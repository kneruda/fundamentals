import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getJson } from "../../api/client";

type Watchlist = { watchlist_id: number; name: string };
const ActiveWatchlistContext = createContext<{ id: number | null; setId: (id: number | null) => void }>({ id: null, setId: () => undefined });
export function ActiveWatchlistProvider({ children }: { children: ReactNode }) { const [id, setId] = useState<number | null>(null); return <ActiveWatchlistContext.Provider value={{ id, setId }}>{children}</ActiveWatchlistContext.Provider>; }
export function WatchlistSelector() { const { id, setId } = useContext(ActiveWatchlistContext); const [lists, setLists] = useState<Watchlist[]>([]); useEffect(() => { void getJson<Watchlist[]>("watchlists").then(setLists); }, []); return <select aria-label="Active watchlist" className="watchlist-select" value={id ?? ""} onChange={event => setId(event.target.value ? Number(event.target.value) : null)}><option value="">Full universe</option>{lists.map(list => <option value={list.watchlist_id} key={list.watchlist_id}>{list.name}</option>)}</select>; }
export function useActiveWatchlist() { return useContext(ActiveWatchlistContext); }
