import { useEffect, useState, type FormEvent } from "react";
import { getJson, requestJson } from "../../api/client";

type Watchlist = { watchlist_id: number; name: string; member_count: number };

export function WatchlistsPage() {
  const [lists, setLists] = useState<Watchlist[]>([]);
  const [name, setName] = useState("");
  const [tickers, setTickers] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = async () => setLists(await getJson<Watchlist[]>("watchlists"));
  useEffect(() => { void load().catch(error => setError(error.message)); }, []);
  async function create(event: FormEvent) { event.preventDefault(); try { await requestJson("watchlists", "POST", { name, tickers: tickers.split(/[\s,]+/).filter(Boolean) }); setName(""); setTickers(""); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to create watchlist"); } }
  async function remove(id: number) { try { await requestJson<void>(`watchlists/${id}`, "DELETE"); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to delete watchlist"); } }
  return <main className="shell"><header><p className="eyebrow">Fundamentals dashboard</p><h1>Watchlists</h1><p className="lede">Save and manage snapshot subsets of your universe.</p></header><form className="ticker-form" onSubmit={create}><label>Name<input required value={name} onChange={event => setName(event.target.value)} /></label><label>Tickers<input required placeholder="AAPL, MSFT" value={tickers} onChange={event => setTickers(event.target.value)} /></label><button>Create watchlist</button></form>{error && <p className="notice error" role="alert">{error}</p>}<ul className="watchlists">{lists.map(list => <li key={list.watchlist_id}><div><strong>{list.name}</strong><span>{list.member_count} members</span></div><button onClick={() => void remove(list.watchlist_id)}>Delete</button></li>)}</ul></main>;
}
