import { useState } from "react";

type Props = { screen: string; onSubmit: (filters: Record<string, unknown>) => void };
const fields: Record<string, Array<[string, string]>> = { absolute_valuation: [["max_pe", "Max P/E"], ["max_ps", "Max P/S"], ["min_fcf_yield", "Min FCF yield %"]], growth: [["min_rev_yoy", "Min revenue YoY %"], ["min_eps_yoy", "Min EPS YoY %"]], quality: [["min_roe", "Min ROE %"], ["min_roic", "Min ROIC %"]], balance_sheet: [["max_net_debt_ebitda", "Max net debt / EBITDA"], ["min_current_ratio", "Min current ratio"]], income: [["min_yield", "Min dividend yield %"], ["max_payout", "Max payout ratio %"]], relative_history: [["years", "History years"], ["max_pe_rank", "Max P/E rank %"]] };
export function ScreenFilters({ screen, onSubmit }: Props) {
  const [values, setValues] = useState<Record<string, string>>({});
  const current = fields[screen] ?? [];

  return <form onSubmit={event => {
    event.preventDefault();
    onSubmit(Object.fromEntries(Object.entries(values).filter(([, value]) => value !== "").map(([key, value]) => [key, Number(value)])));
  }}><h2>Filters</h2>{current.map(([key, label]) => <label key={key}>{label}<input type="number" value={values[key] ?? ""} onChange={event => setValues({ ...values, [key]: event.target.value })}/></label>)}<button type="submit">Apply filters</button></form>;
}
