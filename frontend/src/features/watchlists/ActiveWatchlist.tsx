import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { getJson } from "../../api/client";
import type { Watchlist } from "./watchlistTypes";

const WATCHLISTS_CHANGED = "fundamentals:watchlists-changed";

type ActiveWatchlistContextValue = {
  id: number | null;
  setId: (id: number | null) => void;
  watchlists: Watchlist[];
  refreshWatchlists: () => Promise<void>;
};

const ActiveWatchlistContext = createContext<ActiveWatchlistContextValue>({
  id: null,
  setId: () => undefined,
  watchlists: [],
  refreshWatchlists: async () => undefined,
});

export function notifyWatchlistsChanged() {
  window.dispatchEvent(new Event(WATCHLISTS_CHANGED));
}

export function ActiveWatchlistProvider({ children }: { children: ReactNode }) {
  const [id, setId] = useState<number | null>(null);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);

  const refreshWatchlists = useCallback(async () => {
    const next = await getJson<Watchlist[]>("watchlists");
    setWatchlists(next);
    setId((current) => (
      current !== null && !next.some((list) => list.watchlist_id === current) ? null : current
    ));
  }, []);

  useEffect(() => {
    let current = true;
    void refreshWatchlists().catch(() => {
      if (current) setWatchlists([]);
    });
    return () => {
      current = false;
    };
  }, [refreshWatchlists]);

  useEffect(() => {
    const refresh = () => void refreshWatchlists();
    window.addEventListener(WATCHLISTS_CHANGED, refresh);
    return () => window.removeEventListener(WATCHLISTS_CHANGED, refresh);
  }, [refreshWatchlists]);

  const value = useMemo(
    () => ({ id, setId, watchlists, refreshWatchlists }),
    [id, refreshWatchlists, watchlists],
  );
  return <ActiveWatchlistContext.Provider value={value}>{children}</ActiveWatchlistContext.Provider>;
}

export function WatchlistSelector() {
  const { id, setId, watchlists } = useContext(ActiveWatchlistContext);
  return <select aria-label="Active watchlist" className="watchlist-select" value={id ?? ""} onChange={(event) => setId(event.target.value ? Number(event.target.value) : null)}>
    <option value="">Full universe</option>
    {watchlists.map((list) => <option value={list.watchlist_id} key={list.watchlist_id}>{list.name}</option>)}
  </select>;
}

export function useActiveWatchlist() {
  return useContext(ActiveWatchlistContext);
}
