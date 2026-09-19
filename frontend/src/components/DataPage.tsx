import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTable, type TableResponse } from "../api/client";
import { DataGrid } from "./DataGrid";
import { useActiveWatchlist } from "../features/watchlists/ActiveWatchlist";

export function DataPage({ title, copy, path }: { title: string; copy: string; path: string }) {
 const { id } = useActiveWatchlist();
 const navigate = useNavigate();
 const [data, setData] = useState<TableResponse | null>(null); const [error, setError] = useState<string | null>(null);
 useEffect(() => { const scopedPath = id && path === "dashboard" ? `${path}?watchlist_id=${id}` : path; void getTable(scopedPath).then(setData).catch(error => setError(error.message)); }, [path, id]);
 const watchlistCopy = id ? "Showing the active watchlist; sector and percentile comparisons remain based on the full universe." : "Showing the full active universe.";
 return <main className="shell"><header><p className="eyebrow">Fundamentals dashboard</p><h1>{title}</h1><p className="lede">{copy}</p></header><div className="dashboard-context"><p>{watchlistCopy}</p>{data && <span>{data.rows.length.toLocaleString()} companies</span>}</div>{error ? <p role="alert" className="notice error">{error}</p> : data ? data.rows.length ? <DataGrid data={data} onTickerSelect={(ticker) => navigate(`/company?ticker=${encodeURIComponent(ticker)}`)}/> : <p className="notice">No data available.</p> : <div className="skeleton" aria-label="Loading"/>}</main>;
}
