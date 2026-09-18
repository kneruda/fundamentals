import { useEffect, useState } from "react";
import { getTable, type TableResponse } from "../api/client";
import { DataGrid } from "./DataGrid";
import { useActiveWatchlist } from "../features/watchlists/ActiveWatchlist";

export function DataPage({ title, copy, path }: { title: string; copy: string; path: string }) {
 const { id } = useActiveWatchlist();
 const [data, setData] = useState<TableResponse | null>(null); const [error, setError] = useState<string | null>(null);
 useEffect(() => { const scopedPath = id && path === "dashboard" ? `${path}?watchlist_id=${id}` : path; void getTable(scopedPath).then(setData).catch(error => setError(error.message)); }, [path, id]);
 return <main className="shell"><header><p className="eyebrow">Fundamentals dashboard</p><h1>{title}</h1><p className="lede">{copy}</p></header>{error ? <p role="alert" className="notice error">{error}</p> : data ? data.rows.length ? <DataGrid data={data}/> : <p className="notice">No data available.</p> : <div className="skeleton" aria-label="Loading"/>}</main>;
}
