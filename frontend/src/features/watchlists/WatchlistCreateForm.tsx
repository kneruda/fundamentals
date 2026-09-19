import { useState, type ChangeEvent, type FormEvent } from "react";

type WatchlistCreateFormProps = {
  busy: boolean;
  onCreate: (name: string, description: string, text: string) => Promise<boolean>;
};

export function WatchlistCreateForm({ busy, onCreate }: WatchlistCreateFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [text, setText] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (await onCreate(name, description, text)) {
      setName("");
      setDescription("");
      setText("");
    }
  }

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) setText(await file.text());
  }

  return <form className="watchlist-create" onSubmit={(event) => void submit(event)}>
    <div className="panel-heading">
      <div>
        <p className="eyebrow">New snapshot</p>
        <h2>Create a watchlist</h2>
        <p>Watchlists freeze the members you save. They filter displayed rows without changing full-universe benchmarks.</p>
      </div>
    </div>
    <div className="watchlist-create__fields">
      <label htmlFor="watchlist-name">Name<input id="watchlist-name" required value={name} onChange={(event) => setName(event.target.value)} placeholder="Core compounders" /></label>
      <label htmlFor="watchlist-description">Description <span>(optional)</span><input id="watchlist-description" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Long-term research list" /></label>
    </div>
    <label htmlFor="watchlist-tickers">Tickers<textarea id="watchlist-tickers" required value={text} onChange={(event) => setText(event.target.value)} placeholder={"AAPL\nMSFT\n# comments are allowed"} /></label>
    <div className="watchlist-create__actions">
      <label className="file-input" htmlFor="watchlist-file">Upload .txt<input id="watchlist-file" type="file" accept=".txt,text/plain" onChange={(event) => void chooseFile(event)} /></label>
      <button disabled={busy} type="submit">Create watchlist</button>
    </div>
  </form>;
}
