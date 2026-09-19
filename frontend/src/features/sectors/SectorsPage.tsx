import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { getTable, type TableResponse } from "../../api/client";
import { DataGrid } from "../../components/DataGrid";
import { useActiveWatchlist } from "../watchlists/ActiveWatchlist";

function messageFrom(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

const summaryLabels: Record<string, string> = {
  sector: "Sector",
  n_tickers: "# Tickers",
  median_pe: "Med P/E",
  median_ps: "Med P/S",
  median_pb: "Med P/B",
  median_ev_ebitda: "Med EV/EBITDA",
  median_fcf_yield_pct: "Med FCF Yield %",
  median_rev_yoy_pct: "Med Rev YoY %",
  median_eps_yoy_pct: "Med EPS YoY %",
  median_div_yield_pct: "Med Div Yield %",
};

const constituentLabels: Record<string, string> = {
  ticker: "Ticker",
  name: "Name",
  sub_industry: "Sub-industry",
  price: "Price",
  mktcap_b: "Mkt Cap ($B)",
  pe_trailing: "P/E",
  ps_trailing: "P/S",
  pb_trailing: "P/B",
  ev_ebitda_trailing: "EV/EBITDA",
  fcf_yield_pct: "FCF Yield %",
  rev_yoy_pct: "Rev YoY %",
  eps_yoy_pct: "EPS YoY %",
  div_yield_pct: "Div Yield %",
};

function withLabels(data: TableResponse, labels: Record<string, string>): TableResponse {
  return { ...data, columns: data.columns.map((column) => ({ ...column, label: labels[column.key] ?? column.label })) };
}

export function SectorsPage() {
  const navigate = useNavigate();
  const { id, watchlists } = useActiveWatchlist();
  const [summary, setSummary] = useState<TableResponse | null>(null);
  const [activeSector, setActiveSector] = useState<string | null>(null);
  const [constituents, setConstituents] = useState<TableResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [constituentsError, setConstituentsError] = useState<string | null>(null);
  const [loadingConstituents, setLoadingConstituents] = useState(false);

  useEffect(() => {
    let current = true;
    void getTable("sectors")
      .then((data) => { if (current) setSummary(data); })
      .catch((reason: unknown) => {
        if (current) setSummaryError(messageFrom(reason, "Unable to load sector summary."));
      });
    return () => { current = false; };
  }, []);

  useEffect(() => {
    if (!activeSector) {
      setConstituents(null);
      setConstituentsError(null);
      return;
    }
    let current = true;
    setLoadingConstituents(true);
    setConstituents(null);
    setConstituentsError(null);
    const scope = id === null ? "" : `?watchlist_id=${id}`;
    void getTable(`sectors/${encodeURIComponent(activeSector)}/constituents${scope}`)
      .then((data) => { if (current) setConstituents(data); })
      .catch((reason: unknown) => {
        if (current) setConstituentsError(messageFrom(reason, "Unable to load sector constituents."));
      })
      .finally(() => { if (current) setLoadingConstituents(false); });
    return () => { current = false; };
  }, [activeSector, id]);

  const activeWatchlistName = useMemo(
    () => watchlists.find((watchlist) => watchlist.watchlist_id === id)?.name ?? "Full universe",
    [id, watchlists],
  );

  const chooseSector = (sector: string) => {
    setActiveSector((current) => current === sector ? null : sector);
  };

  return <main className="shell sectors-shell">
    <header>
      <p className="eyebrow">Fundamentals dashboard</p>
      <h1>Sectors</h1>
      <p className="lede">Compare median trailing fundamentals across every active company, then inspect the companies behind each sector.</p>
    </header>

    <section className="sector-context" aria-label="Sector comparison scope">
      <div>
        <strong>Benchmarks use the full active universe.</strong>
        <p>Sector medians and ticker counts never change with a watchlist selection.</p>
      </div>
      <div>
        <strong>Constituents: {activeWatchlistName}</strong>
        <p>{id === null ? "Showing every active company." : "Only companies in the active watchlist are shown below."}</p>
      </div>
    </section>

    {summaryError && <p className="notice error" role="alert">{summaryError}</p>}
    {!summary && !summaryError && <div className="skeleton" aria-busy="true">Loading sector summary…</div>}
    {summary && (summary.rows.length ? <>
      <section className="sector-summary-panel" aria-labelledby="sector-summary-heading">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Full-universe medians</p>
            <h2 id="sector-summary-heading">Sector comparison</h2>
            <p>Multiples, growth, yield, and counts are calculated from the full active universe.</p>
          </div>
        </div>
        <DataGrid data={withLabels(summary, summaryLabels)} />
      </section>

      <section className="sector-drilldown" aria-labelledby="sector-drilldown-heading">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Constituent drill-down</p>
            <h2 id="sector-drilldown-heading">Explore a sector</h2>
            <p>Expand one sector to load its constituent companies. Select any ticker to open its deep dive.</p>
          </div>
        </div>
        <div className="sector-list">
          {summary.rows.map((row) => {
            const sector = String(row.sector);
            const isOpen = activeSector === sector;
            return <details className="sector-item" key={sector} open={isOpen} onToggle={(event) => {
              if ((event.currentTarget as HTMLDetailsElement).open) chooseSector(sector);
              else if (activeSector === sector) setActiveSector(null);
            }}>
              <summary>
                <span>{sector}</span>
                <small>{Number(row.n_tickers).toLocaleString()} companies in benchmark</small>
              </summary>
              <div className="sector-item__body">
                {loadingConstituents && isOpen && <div className="skeleton sector-loading" aria-busy="true">Loading constituents…</div>}
                {constituentsError && isOpen && <p className="notice error" role="alert">{constituentsError}</p>}
                {constituents && isOpen && (constituents.rows.length
                  ? <DataGrid data={withLabels(constituents, constituentLabels)} onTickerSelect={(ticker) => navigate(`/company?ticker=${encodeURIComponent(ticker)}`)} />
                  : <p className="notice sector-empty" role="status">No companies in {activeWatchlistName} belong to this sector.</p>)}
              </div>
            </details>;
          })}
        </div>
      </section>
    </> : <p className="notice" role="status">No active tickers are available yet.</p>)}
  </main>;
}
