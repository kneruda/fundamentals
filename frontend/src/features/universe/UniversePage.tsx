import { useCallback, useEffect, useState } from "react";

import { getJson, getTable, requestJson, type TableResponse } from "../../api/client";
import { DataGrid } from "../../components/DataGrid";
import {
  UniverseActions,
  type BulkResult,
  type RefreshJob,
} from "./UniverseActions";
import { UniverseDrilldown } from "./UniverseDrilldown";

type ActionResult = { ticker: string | null; message: string };

function messageFrom(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export function UniversePage() {
  const [universe, setUniverse] = useState<TableResponse | null>(null);
  const [coverage, setCoverage] = useState<TableResponse | null>(null);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  const [drilldownTicker, setDrilldownTicker] = useState<string | null>(null);
  const [refreshJob, setRefreshJob] = useState<RefreshJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [universeData, coverageData] = await Promise.all([
      getTable("universe"),
      getTable("universe/snapshot-coverage"),
    ]);
    setUniverse(universeData);
    setCoverage(coverageData);
  }, []);

  useEffect(() => {
    let current = true;
    void load().catch((reason: unknown) => {
      if (current) setError(messageFrom(reason, "Unable to load universe."));
    });
    return () => {
      current = false;
    };
  }, [load]);

  useEffect(() => {
    if (!refreshJob || !["queued", "running"].includes(refreshJob.status)) {
      if (refreshJob?.status === "complete") void load();
      return;
    }
    const timer = window.setTimeout(() => {
      void getJson<RefreshJob>(`universe/refresh/${refreshJob.job_id}`)
        .then(setRefreshJob)
        .catch((reason: unknown) => setError(messageFrom(reason, "Unable to read refresh status.")));
    }, 750);
    return () => window.clearTimeout(timer);
  }, [load, refreshJob]);

  const refreshData = async () => {
    try {
      await load();
    } catch (reason) {
      setError(messageFrom(reason, "Unable to reload universe."));
    }
  };

  const addTicker = async (ticker: string, notes: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await requestJson<ActionResult>("universe/tickers", "POST", {
        ticker: ticker.trim().toUpperCase(),
        notes: notes.trim() || null,
      });
      setNotice(result.message);
      await refreshData();
    } catch (reason) {
      setError(messageFrom(reason, "Unable to add ticker."));
    } finally {
      setBusy(false);
    }
  };

  const bulkAdd = async (text: string): Promise<BulkResult[]> => {
    setBusy(true);
    setError(null);
    try {
      const result = await requestJson<{ results: BulkResult[] }>("universe/tickers/bulk", "POST", {
        text,
      });
      const succeeded = result.results.filter((item) => item.ok).length;
      setNotice(`${succeeded} of ${result.results.length} tickers processed.`);
      await refreshData();
      return result.results;
    } catch (reason) {
      setError(messageFrom(reason, "Unable to bulk add tickers."));
      return [];
    } finally {
      setBusy(false);
    }
  };

  const refreshAll = async () => {
    setBusy(true);
    setError(null);
    try {
      const job = await requestJson<RefreshJob>("universe/refresh", "POST");
      setRefreshJob(job);
      setNotice("Universe refresh started.");
    } catch (reason) {
      setError(messageFrom(reason, "Unable to start the universe refresh."));
    } finally {
      setBusy(false);
    }
  };

  const refreshTicker = async (ticker: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await requestJson<ActionResult>(`universe/tickers/${ticker}/refresh`, "POST");
      setNotice(result.message);
      await refreshData();
    } catch (reason) {
      setError(messageFrom(reason, `Unable to refresh ${ticker}.`));
    } finally {
      setBusy(false);
    }
  };

  const removeTicker = async (ticker: string) => {
    setBusy(true);
    setError(null);
    try {
      await requestJson<void>(`universe/tickers/${ticker}`, "DELETE");
      setNotice(`${ticker} is now inactive. Its history is preserved.`);
      setSelectedTicker(null);
      await refreshData();
    } catch (reason) {
      setError(messageFrom(reason, `Unable to remove ${ticker}.`));
    } finally {
      setBusy(false);
    }
  };

  const selected = universe?.rows.find((row) => row.ticker === selectedTicker) ?? null;
  const visibleRows = (universe?.rows ?? []).filter((row) => showInactive || row.active === true);
  const visibleUniverse: TableResponse | null = universe && {
    ...universe,
    rows: visibleRows,
    total: visibleRows.length,
  };

  return <main className="shell universe-shell">
    <header>
      <p className="eyebrow">Fundamentals dashboard</p>
      <h1>Universe management</h1>
      <p className="lede">Manage the followed companies that power every screen. Removing a ticker only makes it inactive; its history remains available.</p>
    </header>

    {notice && <p className="notice success" role="status">{notice}</p>}
    {error && <p className="notice error" role="alert">{error}</p>}

    <UniverseActions busy={busy} refreshJob={refreshJob} onAdd={addTicker} onBulk={bulkAdd} onRefreshAll={refreshAll} />

    <section className="universe-table-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Current universe</p>
          <h2>Followed companies</h2>
          <p>Choose a ticker to inspect its loaded prices and statement summaries.</p>
        </div>
        <label className="toggle-control"><input type="checkbox" checked={showInactive} onChange={(event) => setShowInactive(event.target.checked)} /> Show inactive</label>
      </div>
      {visibleUniverse ? <DataGrid data={visibleUniverse} onTickerSelect={setSelectedTicker} /> : <div className="skeleton" aria-busy="true">Loading universe…</div>}
    </section>

    {selected && <section className="selected-ticker" aria-label={`${selected.ticker} controls`}>
      <div>
        <p className="eyebrow">Selected ticker</p>
        <h2>{String(selected.ticker)} <span>{selected.name ? `— ${String(selected.name)}` : ""}</span></h2>
        <p>{selected.active === true ? "Active in screens and comparisons." : "Inactive; re-add it to return it to the active universe."}</p>
      </div>
      <div className="selected-ticker__actions">
        <button className="secondary-button" type="button" onClick={() => setDrilldownTicker(String(selected.ticker))}>View loaded data</button>
        <button type="button" disabled={busy} onClick={() => void refreshTicker(String(selected.ticker))}>{selected.active === true ? "Refresh ticker" : "Re-add ticker"}</button>
        {selected.active === true && <button className="danger-button" type="button" disabled={busy} onClick={() => void removeTicker(String(selected.ticker))}>Make inactive</button>}
      </div>
    </section>}

    <section className="coverage-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Analyst snapshot coverage</p>
          <h2>Forward-data history</h2>
          <p>Forward-looking screens need at least 30 daily snapshots before trend signals become meaningful.</p>
        </div>
      </div>
      {coverage ? <DataGrid data={coverage} /> : <div className="skeleton" aria-busy="true">Loading snapshot coverage…</div>}
    </section>

    {drilldownTicker && <UniverseDrilldown ticker={drilldownTicker} onClose={() => setDrilldownTicker(null)} />}
  </main>;
}
