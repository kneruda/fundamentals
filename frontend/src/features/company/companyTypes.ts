import type { TableResponse } from "../../api/client";

export type Overview = {
  name?: string;
  sector?: string;
  industry?: string;
  price?: number;
  pct_1d?: number;
  mktcap_b?: number;
  currency?: string;
  next_period_end?: string;
};

export type ValuationResponse = {
  history: TableResponse;
  statistics: TableResponse;
};

export type DividendsResponse = {
  latest: Record<string, unknown> | null;
  annual_history: TableResponse;
};

export type TechnicalsResponse = {
  series: TableResponse;
  signals: Record<string, unknown> | null;
};

export type Tab =
  | "valuation"
  | "profitability"
  | "analyst"
  | "earnings"
  | "dividends"
  | "statements"
  | "news"
  | "technicals";

export const tabs: { id: Tab; label: string }[] = [
  { id: "valuation", label: "Valuation" },
  { id: "profitability", label: "Profitability" },
  { id: "analyst", label: "Analyst" },
  { id: "earnings", label: "Earnings" },
  { id: "dividends", label: "Dividends" },
  { id: "statements", label: "Statements" },
  { id: "news", label: "News" },
  { id: "technicals", label: "Technicals" },
];
