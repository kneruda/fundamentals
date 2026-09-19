import { useEffect, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import { requestJson, runFundamentalScreen, type TableResponse } from "../../api/client";
import { ScreenFilters } from "./ScreenFilters";
import { notifyWatchlistsChanged, useActiveWatchlist } from "../watchlists/ActiveWatchlist";

const screens = ["absolute_valuation", "relative_history", "growth", "quality", "balance_sheet", "income"];

export function FundamentalScreenerPage() {
  const { id } = useActiveWatchlist();
  const [screen, setScreen] = useState(screens[0]);
  const [filters, setFilters] = useState<Record<string, unknown>>({});
  const [data, setData] = useState<TableResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [watchlistName, setWatchlistName] = useState("");
  useEffect(() => { void load(); }, [screen]);
  async function load(nextFilters = filters) { setLoading(true); setError(null); try { setData(await runFundamentalScreen(screen, nextFilters, id)); } catch (e) { setError(e instanceof Error ? e.message : "Unable to run screen"); } finally { setLoading(false); } }
  const columns: ColDef[] = (data?.columns ?? []).map(({ key, label }) => ({ field: key, headerName: label, sortable: true, filter: true, flex: 1, minWidth: 120, valueFormatter: ({ value }) => typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value ?? "—" }));
  async function save() { if (!data || !watchlistName.trim()) return; await requestJson("watchlists", "POST", { name: watchlistName.trim(), tickers: data.rows.map(row => String(row.ticker)) }); notifyWatchlistsChanged(); setWatchlistName(""); }
  return <main className="shell"><header><p className="eyebrow">Fundamentals dashboard</p><h1>Fundamental screener</h1><p className="lede">Find companies on trailing valuation, quality, growth, balance-sheet, and income signals.</p></header><section className="workbench"><aside aria-label="Screen filters"><label>Screen<select value={screen} onChange={e => { setScreen(e.target.value); setFilters({}); }}>{screens.map(value => <option key={value} value={value}>{value.replaceAll("_", " ")}</option>)}</select></label><ScreenFilters screen={screen} onSubmit={next => { setFilters(next); void load(next); }} /></aside><section className="results" aria-busy={loading}><div className="results-head"><h2>Matches</h2>{data && <span>{data.total} companies</span>}</div>{error ? <div role="alert" className="notice error">{error}</div> : loading ? <div className="skeleton" aria-label="Loading results"/> : data?.rows.length ? <><div className="ag-theme-quartz grid"><AgGridReact rowData={data.rows} columnDefs={columns} pagination paginationPageSize={50} /></div><div className="ticker-form"><label>Save results as<input value={watchlistName} onChange={e => setWatchlistName(e.target.value)} /></label><button onClick={() => void save()}>Save watchlist</button></div></> : <div className="notice" role="status">No companies match these filters.</div>}</section></section></main>;
}
