import { useEffect, useState } from "react";

import { getJson, type TableResponse } from "../../api/client";
import { DataGrid } from "../../components/DataGrid";

type Fundamentals = {
  income_statement: TableResponse;
  balance_sheet: TableResponse;
  cash_flow: TableResponse;
};
type DrilldownProps = { ticker: string; onClose: () => void };
type Statement = keyof Fundamentals;

export function UniverseDrilldown({ ticker, onClose }: DrilldownProps) {
  const [tab, setTab] = useState<"prices" | "fundamentals">("prices");
  const [pageSize, setPageSize] = useState(100);
  const [page, setPage] = useState(1);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [periodType, setPeriodType] = useState<"quarterly" | "annual">("quarterly");
  const [statement, setStatement] = useState<Statement>("income_statement");
  const [prices, setPrices] = useState<TableResponse | null>(null);
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setPage(1); }, [dateFrom, dateTo, pageSize, ticker]);
  useEffect(() => {
    if (tab !== "prices") return;
    const parameters = new URLSearchParams({ limit: String(pageSize), offset: String((page - 1) * pageSize) });
    if (dateFrom) parameters.set("date_from", dateFrom);
    if (dateTo) parameters.set("date_to", dateTo);
    void getJson<TableResponse>(`companies/${ticker}/prices?${parameters}`).then(setPrices).catch((reason: Error) => setError(reason.message));
  }, [dateFrom, dateTo, page, pageSize, tab, ticker]);
  useEffect(() => {
    if (tab !== "fundamentals") return;
    void getJson<Fundamentals>(`universe/tickers/${ticker}/fundamentals?period_type=${periodType}`).then(setFundamentals).catch((reason: Error) => setError(reason.message));
  }, [periodType, tab, ticker]);

  const totalPages = Math.max(1, Math.ceil((prices?.total ?? 0) / pageSize));
  return <dialog className="universe-drilldown" open aria-labelledby="drilldown-title"><header><div><p className="eyebrow">Ticker drill-down</p><h2 id="drilldown-title">{ticker}</h2></div><button type="button" className="secondary-button" onClick={onClose}>Close</button></header><div className="tabs" role="tablist" aria-label="Drill-down data"><button type="button" role="tab" aria-selected={tab === "prices"} onClick={() => setTab("prices")}>Prices</button><button type="button" role="tab" aria-selected={tab === "fundamentals"} onClick={() => setTab("fundamentals")}>Fundamentals</button></div>{error && <p className="notice error" role="alert">{error}</p>}{tab === "prices" && <section><div className="drilldown-controls"><label>Rows<select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>{[50, 100, 250, 500].map((size) => <option key={size} value={size}>{size}</option>)}</select></label><label>From<input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label><label>To<input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label></div>{prices ? <><p className="table-caption">{prices.total?.toLocaleString()} rows · page {page} of {totalPages}</p><DataGrid data={prices} /><div className="pagination"><button className="secondary-button" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button><button className="secondary-button" type="button" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button></div></> : <div className="skeleton" aria-busy="true">Loading prices…</div>}</section>}{tab === "fundamentals" && <section><fieldset className="segmented"><legend>Period</legend>{(["quarterly", "annual"] as const).map((option) => <button type="button" className={periodType === option ? "is-selected" : ""} aria-pressed={periodType === option} key={option} onClick={() => setPeriodType(option)}>{option}</button>)}</fieldset><div className="tabs" role="tablist" aria-label="Statement"><button type="button" role="tab" aria-selected={statement === "income_statement"} onClick={() => setStatement("income_statement")}>Income statement</button><button type="button" role="tab" aria-selected={statement === "balance_sheet"} onClick={() => setStatement("balance_sheet")}>Balance sheet</button><button type="button" role="tab" aria-selected={statement === "cash_flow"} onClick={() => setStatement("cash_flow")}>Cash flow</button></div>{fundamentals ? <DataGrid data={fundamentals[statement]} /> : <div className="skeleton" aria-busy="true">Loading fundamentals…</div>}</section>}</dialog>;
}
