import type { EChartsOption } from "echarts";
import { useState, type ReactNode } from "react";

import type { TableResponse } from "../../api/client";
import { DataGrid } from "../../components/DataGrid";
import { CompanyChart } from "./CompanyChart";
import { asNumber, dateLabels, displayCurrency, displayNumber, displayPercent } from "./companyFormat";
import type { DividendsResponse, Overview, ValuationResponse } from "./companyTypes";
import { useCompanyData } from "./useCompanyData";

type PanelProps = { ticker: string; overview: Overview | null };

function PanelState({ loading, error, hasRows, children }: { loading: boolean; error: string | null; hasRows: boolean; children: ReactNode }) {
  if (loading) return <div className="skeleton" aria-busy="true">Loading company data…</div>;
  if (error) return <p className="notice error" role="alert">{error}</p>;
  if (!hasRows) return <div className="notice" role="status">No data is available for this company yet.</div>;
  return <>{children}</>;
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>;
}

export function ValuationPanel({ ticker }: PanelProps) {
  const [years, setYears] = useStateValue(5);
  const { data, loading, error } = useCompanyData<ValuationResponse>(`companies/${ticker}/valuation?years=${years}`);
  const rows = data?.history.rows ?? [];
  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    legend: { bottom: 0 },
    grid: { left: 56, right: 24, top: 32, bottom: 52 },
    xAxis: { type: "category", data: dateLabels(rows), boundaryGap: false },
    yAxis: { type: "value", name: "Multiple" },
    series: [
      ["pe_trailing", "P/E"], ["ps_trailing", "P/S"], ["pb_trailing", "P/B"], ["ev_ebitda_trailing", "EV/EBITDA"],
    ].map(([key, name]) => ({ type: "line", name, showSymbol: false, connectNulls: false, data: rows.map((row) => asNumber(row[key])) })),
  };

  return <section className="company-panel" aria-labelledby="valuation-heading">
    <div className="panel-heading"><div><h2 id="valuation-heading">Trailing multiples</h2><p>Current valuation against the company’s own history.</p></div><PeriodControl value={years} onChange={setYears} /></div>
    <PanelState loading={loading} error={error} hasRows={rows.length > 0}>
      <CompanyChart label="Trailing multiples history" option={option} />
      {data && <><h3>Current vs. own history</h3><DataGrid data={data.statistics} /></>}
    </PanelState>
  </section>;
}

export function ProfitabilityPanel({ ticker, overview }: PanelProps) {
  const [periods, setPeriods] = useStateValue(12);
  const { data, loading, error } = useCompanyData<TableResponse>(`companies/${ticker}/profitability?periods=${periods}`);
  const rows = [...(data?.rows ?? [])].reverse();
  const dates = dateLabels(rows, "fiscal_period_end");
  const revenueOption: EChartsOption = barOption(dates, "Quarterly revenue ($B)", rows.map((row) => asNumber(row.revenue_b)), "Revenue");
  const marginsOption: EChartsOption = lineOption(dates, "%", [
    ["Gross", "gross_margin_pct"], ["Operating", "operating_margin_pct"], ["Net", "net_margin_pct"], ["FCF", "fcf_margin_pct"],
  ], rows);
  const roeOption: EChartsOption = barOption(dates, "Return on equity (%)", rows.map((row) => asNumber(row.roe_pct)), "ROE");

  return <section className="company-panel" aria-labelledby="profitability-heading">
    <div className="panel-heading"><div><h2 id="profitability-heading">Profitability</h2><p>Quarterly operating performance in {overview?.currency ?? "the reporting currency"}.</p></div><SelectControl label="Quarters" value={periods} onChange={setPeriods} options={[8, 12, 16]} /></div>
    <PanelState loading={loading} error={error} hasRows={rows.length > 0}>
      <div className="chart-stack"><CompanyChart label="Quarterly revenue" option={revenueOption} /><CompanyChart label="Quarterly margins" option={marginsOption} /><CompanyChart label="Return on equity" option={roeOption} /></div>
      {data && <DataGrid data={data} />}
    </PanelState>
  </section>;
}

export function AnalystPanel({ ticker, overview }: PanelProps) {
  const { data, loading, error } = useCompanyData<TableResponse>(`companies/${ticker}/analyst`);
  const row = data?.rows[0];
  const rating = asNumber(row?.consensus_rating);
  const target = asNumber(row?.target_price);
  const price = overview?.price;
  const upside = target !== null && price ? (target / price - 1) * 100 : null;
  const distribution = [
    ["Strong buy", "n_strong_buy"], ["Buy", "n_buy"], ["Hold", "n_hold"], ["Sell", "n_sell"], ["Strong sell", "n_strong_sell"],
  ] as const;
  const gaugeOption: EChartsOption = { series: [{ type: "gauge", min: 1, max: 5, splitNumber: 4, detail: { formatter: "{value}" }, axisLabel: { formatter: (value: number) => String(value) }, data: rating === null ? [] : [{ value: rating, name: "Consensus rating" }] }] };
  const distributionOption: EChartsOption = {
    tooltip: { trigger: "axis" }, grid: { left: 48, right: 20, top: 28, bottom: 72 }, xAxis: { type: "category", data: distribution.map(([label]) => label), axisLabel: { rotate: 30 } }, yAxis: { type: "value", minInterval: 1 }, series: [{ type: "bar", name: "Analysts", data: distribution.map(([, key]) => asNumber(row?.[key]) ?? 0), itemStyle: { color: "#1f5a3c" } }],
  };

  return <section className="company-panel" aria-labelledby="analyst-heading">
    <div className="panel-heading"><div><h2 id="analyst-heading">Analyst expectations</h2><p>Latest consensus snapshot and target-price context.</p></div></div>
    <PanelState loading={loading} error={error} hasRows={Boolean(row)}>
      <div className="analyst-layout"><CompanyChart label="Consensus rating gauge" option={gaugeOption} /><div className="metrics"><Metric label="Consensus target" value={displayCurrency(target, overview?.currency)} /><Metric label="Implied upside" value={upside === null ? "—" : displayPercent(upside)} /><Metric label="Forward EPS (current year)" value={displayCurrency(row?.eps_est_curr_y, overview?.currency)} /><Metric label="Forward EPS (next year)" value={displayCurrency(row?.eps_est_next_y, overview?.currency)} /></div></div>
      <CompanyChart label="Analyst rating distribution" option={distributionOption} />
      {data && <DataGrid data={data} />}
    </PanelState>
  </section>;
}

export function EarningsPanel({ ticker }: PanelProps) {
  const { data, loading, error } = useCompanyData<TableResponse>(`companies/${ticker}/earnings?limit=16`);
  const rows = [...(data?.rows ?? [])].reverse();
  const dates = dateLabels(rows, "fiscal_period_end");
  const surpriseOption = signedBarOption(dates, "EPS surprise (%)", rows.map((row) => asNumber(row.surprise_percent)), "Surprise");
  const reactionOption = signedBarOption(dates, "Next-day return (%)", rows.map((row) => asNumber(row.next_day_return_pct)), "Return");
  return <section className="company-panel" aria-labelledby="earnings-heading"><div className="panel-heading"><div><h2 id="earnings-heading">Earnings history</h2><p>Reported earnings surprises and the following session’s price reaction.</p></div></div><PanelState loading={loading} error={error} hasRows={rows.length > 0}><div className="chart-stack"><CompanyChart label="EPS surprise history" option={surpriseOption} /><CompanyChart label="Next-day price reaction history" option={reactionOption} /></div>{data && <DataGrid data={data} />}</PanelState></section>;
}

export function DividendsPanel({ ticker, overview }: PanelProps) {
  const { data, loading, error } = useCompanyData<DividendsResponse>(`companies/${ticker}/dividends?years=10`);
  const rows = [...(data?.annual_history.rows ?? [])].reverse();
  const latest = data?.latest;
  const option = barOption(dateLabels(rows, "year"), "Dividends paid per year", rows.map((row) => asNumber(row.n_dividends)), "Dividends");
  return <section className="company-panel" aria-labelledby="dividends-heading"><div className="panel-heading"><div><h2 id="dividends-heading">Dividends</h2><p>Declared distribution details and annual payment history.</p></div></div><PanelState loading={loading} error={error} hasRows={Boolean(latest) || rows.length > 0}>{latest && <div className="metrics"><Metric label="Forward annual rate" value={displayCurrency(latest.fwd_div_rate, overview?.currency)} hint={`Ex-date: ${String(latest.ex_date ?? "—")}`} /><Metric label="Forward yield" value={displayPercent(latest.fwd_div_yield)} hint={`Pay date: ${String(latest.pay_date ?? "—")}`} /><Metric label="Payout ratio" value={displayPercent(latest.payout_ratio)} /></div>}{rows.length > 0 && <CompanyChart label="Dividend payments per year" option={option} />}{data && <DataGrid data={data.annual_history} />}</PanelState></section>;
}

function PeriodControl({ value, onChange }: { value: number; onChange: (value: number) => void }) { return <fieldset className="segmented"><legend>Period</legend>{[1, 3, 5].map((option) => <button type="button" className={value === option ? "is-selected" : ""} key={option} aria-pressed={value === option} onClick={() => onChange(option)}>{option}Y</button>)}</fieldset>; }
function SelectControl({ label, value, onChange, options }: { label: string; value: number; onChange: (value: number) => void; options: number[] }) { const id = `company-${label.toLowerCase()}`; return <label className="control" htmlFor={id}>{label}<select id={id} value={value} onChange={(event) => onChange(Number(event.target.value))}>{options.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>; }
function useStateValue(initial: number): [number, (value: number) => void] { const [value, setValue] = useState(initial); return [value, setValue]; }
function lineOption(dates: string[], yName: string, series: string[][], rows: Record<string, unknown>[]): EChartsOption { return { tooltip: { trigger: "axis" }, legend: { bottom: 0 }, grid: { left: 56, right: 24, top: 28, bottom: 52 }, xAxis: { type: "category", data: dates, boundaryGap: false }, yAxis: { type: "value", name: yName }, series: series.map(([name, key]) => ({ type: "line", name, showSymbol: false, data: rows.map((row) => asNumber(row[key])) })) }; }
function barOption(dates: string[], title: string, values: (number | null)[], name: string): EChartsOption { return { title: { text: title, left: 0, textStyle: { fontSize: 14 } }, tooltip: { trigger: "axis" }, grid: { left: 56, right: 24, top: 52, bottom: 30 }, xAxis: { type: "category", data: dates }, yAxis: { type: "value" }, series: [{ type: "bar", name, data: values, itemStyle: { color: "#1f5a3c" } }] }; }
function signedBarOption(dates: string[], title: string, values: (number | null)[], name: string): EChartsOption { return { ...barOption(dates, title, values, name), series: [{ type: "bar", name, data: values.map((value) => ({ value, itemStyle: { color: (value ?? 0) >= 0 ? "#1f5a3c" : "#a64040" } })) }] }; }
