import { useState } from "react";

import { getJson, requestJson } from "../../api/client";
import {
  notifyWatchlistsChanged,
  useActiveWatchlist,
} from "./ActiveWatchlist";
import { WatchlistCreateForm } from "./WatchlistCreateForm";
import { WatchlistEditor } from "./WatchlistEditor";
import { WatchlistList } from "./WatchlistList";
import type { Watchlist, WatchlistDetail } from "./watchlistTypes";

function messageFrom(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

export function WatchlistsPage() {
  const { id: activeId, setId: setActiveId, watchlists, refreshWatchlists } = useActiveWatchlist();
  const [selected, setSelected] = useState<WatchlistDetail | null>(null);
  const [editing, setEditing] = useState<WatchlistDetail | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Watchlist | null>(null);
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    await refreshWatchlists();
    notifyWatchlistsChanged();
  }

  async function create(name: string, description: string, text: string): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      const result = await requestJson<WatchlistDetail>("watchlists", "POST", {
        name: name.trim(),
        description: description.trim() || null,
        text,
      });
      await refresh();
      setSelected(result);
      setNotice(`Created “${result.name}” with ${result.member_count} members.`);
      return true;
    } catch (reason) {
      setError(messageFrom(reason, "Unable to create watchlist."));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function select(list: Watchlist) {
    if (selected?.watchlist_id === list.watchlist_id) {
      setSelected(null);
      return;
    }
    setLoadingId(list.watchlist_id);
    setError(null);
    try {
      setSelected(await getJson<WatchlistDetail>(`watchlists/${list.watchlist_id}`));
    } catch (reason) {
      setError(messageFrom(reason, "Unable to load watchlist members."));
    } finally {
      setLoadingId(null);
    }
  }

  async function save(name: string, text: string): Promise<boolean> {
    if (!editing) return false;
    setBusy(true);
    setError(null);
    try {
      let detail = editing;
      if (name.trim() !== editing.name) {
        detail = await requestJson<WatchlistDetail>(`watchlists/${editing.watchlist_id}`, "PATCH", {
          name: name.trim(),
        });
      }
      detail = await requestJson<WatchlistDetail>(`watchlists/${editing.watchlist_id}`, "PUT", { text });
      await refresh();
      setSelected(detail);
      setNotice(`Updated “${detail.name}” with ${detail.member_count} members.`);
      return true;
    } catch (reason) {
      setError(messageFrom(reason, "Unable to update watchlist."));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    setError(null);
    try {
      await requestJson<void>(`watchlists/${deleteTarget.watchlist_id}`, "DELETE");
      if (activeId === deleteTarget.watchlist_id) setActiveId(null);
      if (selected?.watchlist_id === deleteTarget.watchlist_id) setSelected(null);
      setNotice(`Deleted “${deleteTarget.name}”.`);
      setDeleteTarget(null);
      await refresh();
    } catch (reason) {
      setError(messageFrom(reason, "Unable to delete watchlist."));
    } finally {
      setBusy(false);
    }
  }

  return <main className="shell watchlists-shell">
    <header>
      <p className="eyebrow">Fundamentals dashboard</p>
      <h1>Watchlists</h1>
      <p className="lede">Save focused, named subsets of your universe and use one as the display scope across the dashboard.</p>
    </header>
    {notice && <p className="notice success" role="status">{notice}</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
    <WatchlistCreateForm busy={busy} onCreate={create} />
    <WatchlistList lists={watchlists} selected={selected} loadingId={loadingId} busy={busy} onSelect={(list) => void select(list)} onEdit={setEditing} onDelete={setDeleteTarget} />
    {editing && <WatchlistEditor detail={editing} busy={busy} onClose={() => setEditing(null)} onSave={save} />}
    {deleteTarget && <DeleteWatchlistDialog watchlist={deleteTarget} busy={busy} onCancel={() => setDeleteTarget(null)} onConfirm={() => void confirmDelete()} />}
  </main>;
}

function DeleteWatchlistDialog({ watchlist, busy, onCancel, onConfirm }: { watchlist: Watchlist; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  return <dialog className="watchlist-dialog watchlist-dialog--confirm" open aria-modal="true" aria-labelledby="delete-watchlist-title">
    <h2 id="delete-watchlist-title">Delete “{watchlist.name}”?</h2>
    <p>This removes the saved snapshot and its memberships. It does not remove any tickers from your universe.</p>
    <div className="watchlist-dialog__actions"><button className="secondary-button" type="button" onClick={onCancel}>Cancel</button><button className="danger-button" disabled={busy} type="button" onClick={onConfirm}>Delete watchlist</button></div>
  </dialog>;
}
