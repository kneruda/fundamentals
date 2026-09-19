import type { Watchlist, WatchlistDetail } from "./watchlistTypes";

type WatchlistListProps = {
  lists: Watchlist[];
  selected: WatchlistDetail | null;
  loadingId: number | null;
  busy: boolean;
  onSelect: (watchlist: Watchlist) => void;
  onEdit: (watchlist: WatchlistDetail) => void;
  onDelete: (watchlist: Watchlist) => void;
};

function memberLabel(count: number) {
  return `${count} ${count === 1 ? "member" : "members"}`;
}

export function WatchlistList({ lists, selected, loadingId, busy, onSelect, onEdit, onDelete }: WatchlistListProps) {
  if (!lists.length) return <section className="watchlist-empty" role="status"><h2>No watchlists yet</h2><p>Create your first snapshot list above to focus screen results on a selected group of companies.</p></section>;

  return <section className="watchlist-list" aria-labelledby="existing-watchlists-title">
    <div className="panel-heading"><div><p className="eyebrow">Saved snapshots</p><h2 id="existing-watchlists-title">Existing watchlists</h2></div><span>{lists.length} saved</span></div>
    <ul>
      {lists.map((list) => {
        const expanded = selected?.watchlist_id === list.watchlist_id;
        return <li key={list.watchlist_id} className={expanded ? "watchlist-row is-expanded" : "watchlist-row"}>
          <button className="watchlist-row__summary" type="button" aria-expanded={expanded} onClick={() => onSelect(list)}>
            <span><strong>{list.name}</strong>{list.description && <small>{list.description}</small>}</span>
            <span>{loadingId === list.watchlist_id ? "Loading…" : memberLabel(list.member_count)}</span>
          </button>
          {expanded && selected && <div className="watchlist-row__detail">
            <p><strong>Members</strong></p>
            <p className="watchlist-members">{selected.tickers.length ? selected.tickers.join(", ") : "No members"}</p>
            <p className="input-help">Created {selected.created_at ? new Date(selected.created_at).toLocaleDateString() : "—"}</p>
            <div className="watchlist-row__actions"><button className="secondary-button" type="button" onClick={() => onEdit(selected)}>Edit list</button><button className="danger-button" type="button" disabled={busy} onClick={() => onDelete(list)}>Delete</button></div>
          </div>}
        </li>;
      })}
    </ul>
  </section>;
}
