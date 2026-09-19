import { useState, type ChangeEvent, type FormEvent } from "react";

type BulkResult = { ticker: string; ok: boolean; message: string };
type RefreshJob = {
  job_id: string;
  status: "queued" | "running" | "complete" | "failed";
  total: number;
  fetched: number;
  ingested: number;
  failed: number;
  current_ticker: string | null;
  results: BulkResult[];
  error: string | null;
};

type UniverseActionsProps = {
  busy: boolean;
  refreshJob: RefreshJob | null;
  onAdd: (ticker: string, notes: string) => Promise<void>;
  onBulk: (text: string) => Promise<BulkResult[]>;
  onRefreshAll: () => Promise<void>;
};

export function UniverseActions({ busy, refreshJob, onAdd, onBulk, onRefreshAll }: UniverseActionsProps) {
  return <section className="universe-actions" aria-label="Universe actions">
    <AddTickerForm busy={busy} onAdd={onAdd} />
    <BulkTickerForm busy={busy} onBulk={onBulk} />
    <RefreshAllControl busy={busy} job={refreshJob} onRefreshAll={onRefreshAll} />
  </section>;
}

function AddTickerForm({ busy, onAdd }: { busy: boolean; onAdd: (ticker: string, notes: string) => Promise<void> }) {
  const [ticker, setTicker] = useState("");
  const [notes, setNotes] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onAdd(ticker, notes);
    setTicker("");
    setNotes("");
  }
  return <form className="universe-card" onSubmit={(event) => void submit(event)}><h2>Add a ticker</h2><p>New symbols are backfilled before joining the active universe.</p><label htmlFor="universe-ticker">Ticker<input id="universe-ticker" required value={ticker} onChange={(event) => setTicker(event.target.value)} placeholder="AAPL" autoCapitalize="characters" spellCheck="false" /></label><label htmlFor="universe-notes">Notes <span>(optional)</span><input id="universe-notes" value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Earnings follow-up" /></label><button disabled={busy} type="submit">Add ticker</button></form>;
}

function BulkTickerForm({ busy, onBulk }: { busy: boolean; onBulk: (text: string) => Promise<BulkResult[]> }) {
  const [text, setText] = useState("");
  const [results, setResults] = useState<BulkResult[]>([]);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setResults(await onBulk(text)); setText(""); }
  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) setText(await file.text());
  }
  return <form className="universe-card universe-card--bulk" onSubmit={(event) => void submit(event)}><h2>Bulk add</h2><p>Paste lines or upload a text file. Comments and blank lines are parsed by the shared server-side ticker parser.</p><label htmlFor="universe-bulk">Tickers<textarea id="universe-bulk" required value={text} onChange={(event) => setText(event.target.value)} placeholder={"AAPL\nMSFT\n# optional comment"} /></label><label className="file-input" htmlFor="universe-file">Upload .txt<input id="universe-file" type="file" accept=".txt,text/plain" onChange={(event) => void chooseFile(event)} /></label><button disabled={busy} type="submit">Add all</button>{results.length > 0 && <BulkResults results={results} />}</form>;
}

function RefreshAllControl({ busy, job, onRefreshAll }: { busy: boolean; job: RefreshJob | null; onRefreshAll: () => Promise<void> }) {
  const running = job?.status === "queued" || job?.status === "running";
  const progress = job?.total ? Math.round((job.ingested / job.total) * 100) : 0;
  return <section className="universe-card universe-card--refresh"><h2>Refresh active universe</h2><p>Fetches run in parallel; warehouse writes remain serialized to preserve DuckDB’s single-writer guarantee.</p><button type="button" disabled={busy || running} onClick={() => void onRefreshAll()}>{running ? "Refresh running…" : "Refresh all"}</button>{job && <div className="job-progress" role="status" aria-live="polite"><div><strong>{job.status === "complete" ? "Refresh complete" : "Refreshing"}</strong><span>{job.ingested} / {job.total} ingested · {job.failed} failed</span></div><progress value={progress} max="100">{progress}%</progress>{job.current_ticker && <small>Ingesting {job.current_ticker}</small>}{job.error && <small className="error-text">{job.error}</small>}</div>}</section>;
}

function BulkResults({ results }: { results: BulkResult[] }) { const succeeded = results.filter((result) => result.ok).length; return <div className="bulk-results" role="status"><strong>{succeeded} of {results.length} processed</strong><ul>{results.map((result) => <li key={result.ticker}><span>{result.ticker}</span><span>{result.ok ? "Ready" : "Failed"} · {result.message}</span></li>)}</ul></div>; }

export type { RefreshJob, BulkResult };
