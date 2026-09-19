import { AgGridReact } from "ag-grid-react";
import type { ColDef, ICellRendererParams } from "ag-grid-community";
import type { TableResponse } from "../api/client";

type DataGridProps = {
  data: TableResponse;
  onTickerSelect?: (ticker: string) => void;
};

const percentageFields = new Set([
  "pct_1d",
  "rev_yoy_pct",
  "eps_yoy_pct",
  "div_yield_pct",
  "target_upside_pct",
]);
const multipleFields = new Set([
  "pe_trailing",
  "pe_forward",
  "ps_trailing",
  "pb_trailing",
  "ev_ebitda_trailing",
]);

export function DataGrid({ data, onTickerSelect }: DataGridProps) {
  const columnDefs: ColDef[] = data.columns.map(({ key, label }) => ({
    field: key,
    headerName: label,
    sortable: true,
    filter: true,
    minWidth: 120,
    flex: 1,
    cellRenderer: key === "ticker" && onTickerSelect ? (params: ICellRendererParams) => <button className="grid-link" type="button" onClick={() => onTickerSelect(String(params.value))}>{params.value}</button> : undefined,
    cellClassRules: percentageFields.has(key) ? {
      "cell-positive": (params) => typeof params.value === "number" && params.value > 0,
      "cell-negative": (params) => typeof params.value === "number" && params.value < 0,
    } : undefined,
    valueFormatter: ({ value }) => formatValue(key, value),
  }));
  return <div className="ag-theme-quartz grid"><AgGridReact rowData={data.rows} columnDefs={columnDefs} pagination paginationPageSize={50}/></div>;
}

function formatValue(key: string, value: unknown): string {
  if (typeof value !== "number") return value == null ? "—" : String(value);
  if (percentageFields.has(key)) return `${value.toFixed(1)}%`;
  if (key === "price" || key === "target_price") return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  if (key === "mktcap_b") return `$${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}B`;
  if (multipleFields.has(key)) return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  if (key === "consensus_rating") return value.toFixed(2);
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
