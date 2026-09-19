import { useState, type ReactNode } from "react";
import type { EChartsOption } from "echarts";

import type { TableResponse } from "../../api/client";
import { DataGrid } from "../../components/DataGrid";
import { CompanyChart } from "./CompanyChart";
import { asNumber, dateLabels, displayNumber } from "./companyFormat";
import type { TechnicalsResponse } from "./companyTypes";
import { useCompanyData } from "./useCompanyData";

type PanelProps = { ticker: string };
type StatementType = "income_statement" | "balance_sheet" | "cash_flow";
type Units = "billions" | "millions" | "thousands" | "raw";

const statementLabels: Record<StatementType, string> = {
  income_statement: "Income statement",
  balance_sheet: "Balance sheet",
  cash_flow: "Cash flow",
};

function PanelState({ loading, error, hasRows, children }: { loading: boolean; error: string | null; hasRows: boolean; children: ReactNode }) {
  if (loading) return <div className="skeleton" aria-busy="true">Loading company data…</div>;
  if (error) return <p className="notice error" role="alert">{error}</p>;
  if (!hasRows) return <div className="notice" role="status">No data is available for this company yet.</div>;
  return <>{children}</>;
}

export function StatementsPanel({ ticker }: PanelProps) {
  const [statementType, setStatementType] = useState<StatementType>("income_statement");
  const [periodType, setPeriodType] = useState<"quarterly" | "annual">("quarterly");
  const [depth, setDepth] = useState<"summary" | "full">("summary");
  const [units, setUnits] = useState<Units>("billions");
  const path = `companies/${ticker}/statements/${statementType}?period_type=${periodType}&depth=${depth}&limit=8`;
  const { data, loading, error } = useCompanyData<TableResponse>(path);

  return <section className="company-panel" aria-labelledby="statements-heading">
    <div className="panel-heading"><div><h2 id="statements-heading">Financial statements</h2><p>Period-based reported financials. Choose a summary for the standard analytical view.</p></div></div>
    <div className="statement-controls">
      <SegmentedControl label="Period" value={periodType} onChange={setPeriodType} options={[["quarterly", "Quarterly"], ["annual", "Annual"]]} />
      <SegmentedControl label="Depth" value={depth} onChange={setDepth} options={[["summary", "Summary"], ["full", "Full"]]} />
      <label className="control" htmlFor="statement-units">Units<select id="statement-units" value={units} onChange={(event) => setUnits(event.target.value as Units)}><option value="billions">Billions</option><option value="millions">Millions</option><option value="thousands">Thousands</option><option value="raw">Raw</option></select></label>
    </div>
    <div className="tabs statement-tabs" role="tablist" aria-label="Statement type">
      {(Object.keys(statementLabels) as StatementType[]).map((type) => <button type="button" role="tab" aria-selected={statementType === type} className={statementType === type ? "is-selected" : ""} key={type} onClick={() => setStatementType(type)}>{statementLabels[type]}</button>)}
    </div>
    <PanelState loading={loading} error={error} hasRows={(data?.rows.length ?? 0) > 0}>
      {data && <StatementTable data={data} units={units} />}
    </PanelState>
  </section>;
}

export function NewsPanel({ ticker }: PanelProps) {
  const { data, loading, error } = useCompanyData<TableResponse>(`companies/${ticker}/news?limit=50`);
  const rows = data?.rows ?? [];
  return <section className="company-panel" aria-labelledby="news-heading"><div className="panel-heading"><div><h2 id="news-heading">Recent news</h2><p>Latest company coverage from the existing market-data provider.</p></div></div><PanelState loading={loading} error={error} hasRows={rows.length > 0}><ol className="news-list">{rows.map((article, index) => { const content = typeof article.content === "string" ? article.content : ""; return <li key={`${article.link ?? article.date ?? "news"}-${index}`}><time>{String(article.date ?? "")}</time><div><a href={String(article.link ?? "#")} target="_blank" rel="noreferrer">{String(article.title ?? "Untitled article")}</a>{content && <p>{content.slice(0, 400)}{content.length > 400 ? "…" : ""}</p>}</div></li>; })}</ol></PanelState></section>;
}

export function TechnicalsPanel({ ticker }: PanelProps) {
  const [range, setRange] = useState<"6m" | "1y" | "3y" | "5y" | "max">("1y");
  const [candles, setCandles] = useState(false);
  const [bands, setBands] = useState(false);
  const lookbacks = { "6m": 182, "1y": 365, "3y": 1095, "5y": 1825, max: "" };
  const suffix = lookbacks[range] === "" ? "" : `?lookback_days=${lookbacks[range]}`;
  const { data, loading, error } = useCompanyData<TechnicalsResponse>(`companies/${ticker}/technicals${suffix}`);
  const rows = data?.series.rows ?? [];
  const option = technicalOption(rows, candles, bands);
  const signals = data?.signals;

  return <section className="company-panel" aria-labelledby="technicals-heading"><div className="panel-heading"><div><h2 id="technicals-heading">Technicals</h2><p>Price action and deterministic indicators computed from the loaded price history.</p></div><SegmentedControl label="Range" value={range} onChange={setRange} options={[["6m", "6M"], ["1y", "1Y"], ["3y", "3Y"], ["5y", "5Y"], ["max", "Max"]]} /></div><PanelState loading={loading} error={error} hasRows={rows.length > 0}>{signals && <SignalSummary signals={signals} />}<div className="chart-options"><label><input type="checkbox" checked={candles} onChange={(event) => setCandles(event.target.checked)} /> Candlesticks</label><label><input type="checkbox" checked={bands} onChange={(event) => setBands(event.target.checked)} /> Bollinger bands</label></div><CompanyChart label="Technical analysis chart" option={option} height="tall" /></PanelState></section>;
}

function StatementTable({ data, units }: { data: TableResponse; units: Units }) {
  const columns = data.rows.map((row) => String(row.fiscal_period_end ?? "—"));
  const metricKeys = data.columns.map((column) => column.key).filter((key) => !["fiscal_period_end", "ticker", "period_type", "report_date", "currency"].includes(key));
  return <div className="statement-table-wrap"><table className="statement-table"><thead><tr><th scope="col">Metric</th>{columns.map((column) => <th scope="col" key={column}>{column}</th>)}</tr></thead><tbody>{metricKeys.map((key) => <tr key={key}><th scope="row">{key.replaceAll("_", " ")}</th>{data.rows.map((row, index) => <td key={`${key}-${index}`}>{formatStatementValue(row[key], units)}</td>)}</tr>)}</tbody></table></div>;
}

function SignalSummary({ signals }: { signals: Record<string, unknown> }) {
  const rsi = asNumber(signals.rsi_14);
  const macd = asNumber(signals.macd_histogram);
  const volume = asNumber(signals.volume_ratio);
  const cards = [
    ["RSI (14)", displayNumber(rsi, 1), rsi === null ? "—" : rsi < 30 ? "Oversold" : rsi > 70 ? "Overbought" : "Neutral"],
    ["MACD histogram", displayNumber(macd, 3), macd === null ? "—" : macd >= 0 ? "Bullish" : "Bearish"],
    ["From SMA 200", displayRatio(signals.pct_from_sma_200), "Current position"],
    ["From 52-week high", displayRatio(signals.pct_from_52w_high), "Current position"],
    ["Volume ratio", displayNumber(volume, 2), volume !== null && volume > 2 ? "Elevated volume" : "Relative to 50-day average"],
  ];
  return <div className="metrics metrics--signals">{cards.map(([label, value, hint]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong><small>{hint}</small></div>)}</div>;
}

function SegmentedControl<T extends string>({ label, value, onChange, options }: { label: string; value: T; onChange: (value: T) => void; options: [T, string][] }) { return <fieldset className="segmented"><legend>{label}</legend>{options.map(([option, optionLabel]) => <button type="button" className={value === option ? "is-selected" : ""} key={option} aria-pressed={value === option} onClick={() => onChange(option)}>{optionLabel}</button>)}</fieldset>; }
function formatStatementValue(value: unknown, units: Units): string { const number = asNumber(value); if (number === null) return "—"; const divisors: Record<Units, number> = { billions: 1e9, millions: 1e6, thousands: 1e3, raw: 1 }; const suffixes: Record<Units, string> = { billions: "B", millions: "M", thousands: "K", raw: "" }; const scaled = number / divisors[units]; return `${scaled.toLocaleString(undefined, { maximumFractionDigits: units === "raw" ? 0 : 2 })}${suffixes[units]}`; }
function displayRatio(value: unknown): string { const number = asNumber(value); return number === null ? "—" : `${(number * 100).toFixed(1)}%`; }

function technicalOption(rows: Record<string, unknown>[], candles: boolean, bands: boolean): EChartsOption {
  const dates = dateLabels(rows);
  const line = (name: string, key: string, xAxisIndex = 0, yAxisIndex = 0) => ({ type: "line", name, xAxisIndex, yAxisIndex, showSymbol: false, data: rows.map((row) => asNumber(row[key])) });
  const price = candles ? { type: "candlestick", name: "Price", data: rows.map((row) => [asNumber(row.open), asNumber(row.close), asNumber(row.low), asNumber(row.high)]) } : line("Price", "adjusted_close");
  const series: Record<string, unknown>[] = [price, line("SMA 20", "sma_20"), line("SMA 50", "sma_50"), line("SMA 200", "sma_200")];
  if (bands) series.push(line("BB upper", "bb_upper"), line("BB middle", "bb_middle"), line("BB lower", "bb_lower"));
  series.push({ type: "bar", name: "Volume", xAxisIndex: 1, yAxisIndex: 1, data: rows.map((row) => ({ value: asNumber(row.volume), itemStyle: { color: (asNumber(row.close) ?? 0) >= (asNumber(row.open) ?? 0) ? "#1f5a3c" : "#a64040" } })) }, line("Volume SMA 50", "volume_sma_50", 1, 1), { type: "line", name: "RSI 14", xAxisIndex: 2, yAxisIndex: 2, showSymbol: false, data: rows.map((row) => asNumber(row.rsi_14)), markLine: { silent: true, data: [{ yAxis: 30 }, { yAxis: 70 }] } }, line("MACD", "macd", 3, 3), line("Signal", "macd_signal", 3, 3), { type: "bar", name: "MACD histogram", xAxisIndex: 3, yAxisIndex: 3, data: rows.map((row) => ({ value: asNumber(row.macd_histogram), itemStyle: { color: (asNumber(row.macd_histogram) ?? 0) >= 0 ? "#1f5a3c" : "#a64040" } })) });
  return { tooltip: { trigger: "axis" }, legend: { bottom: 0, type: "scroll" }, grid: [{ left: 60, right: 24, top: 24, height: "38%" }, { left: 60, right: 24, top: "48%", height: "11%" }, { left: 60, right: 24, top: "65%", height: "11%" }, { left: 60, right: 24, top: "82%", height: "11%" }], xAxis: [0, 1, 2, 3].map((index) => ({ type: "category", data: dates, gridIndex: index, boundaryGap: index === 0 && candles, axisLabel: { show: index === 3 }, axisTick: { show: index === 3 }, axisLine: { show: index === 3 } })), yAxis: [0, 1, 2, 3].map((index) => ({ type: "value", gridIndex: index, min: index === 2 ? 0 : undefined, max: index === 2 ? 100 : undefined })), dataZoom: [{ type: "inside", xAxisIndex: [0, 1, 2, 3] }, { type: "slider", xAxisIndex: [0, 1, 2, 3], bottom: 22 }], series: series as EChartsOption["series"] };
}
