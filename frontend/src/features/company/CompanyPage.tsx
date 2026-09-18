import { useEffect, useState, type FormEvent } from "react";

import { getJson, getTable, type TableResponse } from "../../api/client";
import { DataGrid } from "../../components/DataGrid";

const tabs = ["valuation", "profitability", "analyst", "earnings", "dividends", "statements", "technicals"] as const;
type Tab = typeof tabs[number];
type Overview = { name?: string; sector?: string; industry?: string; price?: number; mktcap_b?: number; currency?: string };

export function CompanyPage() {
  const [ticker, setTicker] = useState("AAPL"), [selected, setSelected] = useState("AAPL"), [tab, setTab] = useState<Tab>("valuation"), [overview, setOverview] = useState<Overview | null>(null), [table, setTable] = useState<TableResponse | null>(null), [error, setError] = useState<string | null>(null);
  useEffect(() => { void getJson<Overview>(`companies/${selected}/overview`).then(setOverview).catch(e => setError(e.message)); }, [selected]);
  useEffect(() => { const path = tab === "valuation" ? `companies/${selected}/valuation?years=5` : tab === "statements" ? `companies/${selected}/statements/income_statement` : `companies/${selected}/${tab}`; if (tab === "valuation") void getJson<{history:TableResponse}>(path).then(data => setTable(data.history)).catch(e => setError(e.message)); else if (tab === "dividends" || tab === "technicals") void getJson<{annual_history?:TableResponse;series?:TableResponse}>(path).then(data => setTable(data.annual_history ?? data.series ?? null)).catch(e => setError(e.message)); else void getTable(path).then(setTable).catch(e => setError(e.message)); }, [selected, tab]);
  function submit(event: FormEvent) { event.preventDefault(); setSelected(ticker.toUpperCase()); }
  return <main className="shell"><header><p className="eyebrow">Company deep dive</p><h1>{overview?.name ?? selected} ({selected})</h1><p className="lede">{overview?.sector ?? "—"} · {overview?.industry ?? "—"} · {overview?.currency ?? "—"}</p><p>Price: {overview?.price?.toFixed(2) ?? "—"} · Market cap: {overview?.mktcap_b?.toFixed(1) ?? "—"}B</p></header><form className="ticker-form" onSubmit={submit}><label>Ticker<input value={ticker} onChange={e => setTicker(e.target.value)} /></label><button>Load company</button></form><div className="tabs" role="tablist">{tabs.map(item => <button role="tab" aria-selected={tab === item} key={item} onClick={() => setTab(item)}>{item}</button>)}</div>{error ? <p className="notice error">{error}</p> : table ? <DataGrid data={table}/> : <div className="skeleton"/>}</main>;
}
