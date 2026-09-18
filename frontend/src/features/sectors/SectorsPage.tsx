import { useEffect, useState } from "react";
import { getTable, type TableResponse } from "../../api/client";
import { DataGrid } from "../../components/DataGrid";
import { useActiveWatchlist } from "../watchlists/ActiveWatchlist";

export function SectorsPage() {
  const { id } = useActiveWatchlist();
  const [summary, setSummary] = useState<TableResponse | null>(null);
  const [sector, setSector] = useState("");
  const [constituents, setConstituents] = useState<TableResponse | null>(null);
  useEffect(() => { void getTable("sectors").then(setSummary); }, []);
  useEffect(() => { if (sector) void getTable(`sectors/${encodeURIComponent(sector)}/constituents${id ? `?watchlist_id=${id}` : ""}`).then(setConstituents); }, [sector, id]);
  return <main className="shell"><h1>Sectors</h1>{summary ? <><DataGrid data={summary}/><label className="select-label">Sector<select value={sector} onChange={event => setSector(event.target.value)}><option value="">Choose a sector</option>{summary.rows.map(row => <option key={String(row.sector)}>{String(row.sector)}</option>)}</select></label>{constituents && <DataGrid data={constituents}/>}</> : <div className="skeleton"/>}</main>;
}
