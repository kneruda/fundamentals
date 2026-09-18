import { AgGridReact } from "ag-grid-react";
import type { ColDef } from "ag-grid-community";
import type { TableResponse } from "../api/client";

export function DataGrid({ data }: { data: TableResponse }) {
  const columnDefs: ColDef[] = data.columns.map(({ key, label }) => ({ field: key, headerName: label, sortable: true, filter: true, minWidth: 120, flex: 1, valueFormatter: ({ value }) => typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : value ?? "—" }));
  return <div className="ag-theme-quartz grid"><AgGridReact rowData={data.rows} columnDefs={columnDefs} pagination paginationPageSize={50}/></div>;
}
