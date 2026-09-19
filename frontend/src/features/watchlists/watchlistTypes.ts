export type Watchlist = {
  watchlist_id: number;
  name: string;
  description: string | null;
  created_at: string | null;
  member_count: number;
};

export type WatchlistDetail = Watchlist & { tickers: string[] };
