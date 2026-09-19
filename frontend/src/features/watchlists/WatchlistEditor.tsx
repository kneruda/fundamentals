import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";

import type { WatchlistDetail } from "./watchlistTypes";

type WatchlistEditorProps = {
  detail: WatchlistDetail;
  busy: boolean;
  onClose: () => void;
  onSave: (name: string, text: string) => Promise<boolean>;
};

export function WatchlistEditor({ detail, busy, onClose, onSave }: WatchlistEditorProps) {
  const [name, setName] = useState(detail.name);
  const [text, setText] = useState(detail.tickers.join("\n"));
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (await onSave(name, text)) onClose();
  }

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) setText(await file.text());
  }

  return <dialog className="watchlist-dialog" open aria-modal="true" aria-labelledby="watchlist-editor-title">
    <form onSubmit={(event) => void submit(event)}>
      <header>
        <div>
          <p className="eyebrow">Edit watchlist</p>
          <h2 id="watchlist-editor-title">{detail.name}</h2>
        </div>
        <button ref={closeRef} className="secondary-button" type="button" onClick={onClose}>Close</button>
      </header>
      <label htmlFor="watchlist-edit-name">Name<input id="watchlist-edit-name" required value={name} onChange={(event) => setName(event.target.value)} /></label>
      <label htmlFor="watchlist-edit-tickers">Members<textarea id="watchlist-edit-tickers" required value={text} onChange={(event) => setText(event.target.value)} /></label>
      <p className="input-help">One ticker per line. Blank lines and comments are handled by the shared server-side parser.</p>
      <div className="watchlist-dialog__actions">
        <label className="file-input" htmlFor="watchlist-edit-file">Replace with .txt<input id="watchlist-edit-file" type="file" accept=".txt,text/plain" onChange={(event) => void chooseFile(event)} /></label>
        <button disabled={busy} type="submit">Save changes</button>
      </div>
    </form>
  </dialog>;
}
