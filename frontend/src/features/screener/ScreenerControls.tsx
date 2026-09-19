import { useEffect, useState, type FormEvent } from "react";

import { requestJson, type TableResponse } from "../../api/client";
import { notifyWatchlistsChanged } from "../watchlists/ActiveWatchlist";

export type FilterField = {
  key: string;
  label: string;
  type: "number" | "select" | "boolean";
  defaultValue?: number | string | boolean | null;
  min?: number;
  max?: number;
  step?: number;
  optional?: boolean;
  options?: Array<{ label: string; value: string | number | null }>;
};

function defaults(fields: FilterField[]) {
  return Object.fromEntries(fields.map((field) => [field.key, field.defaultValue ?? ""]));
}

export function ScreenerFilterForm({ formKey, fields, onSubmit }: { formKey: string; fields: FilterField[]; onSubmit: (filters: Record<string, unknown>) => void }) {
  const [values, setValues] = useState<Record<string, string | number | boolean | null>>(() => defaults(fields));
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setValues(defaults(fields));
    setEnabled({});
  }, [formKey]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const filters: Record<string, unknown> = {};
    for (const field of fields) {
      if (field.optional && !enabled[field.key]) continue;
      const value = values[field.key];
      if (field.type === "boolean") {
        if (value === true) filters[field.key] = true;
      } else if (field.type === "number" && value !== "") {
        filters[field.key] = Number(value);
      } else if (field.type === "select" && value !== "") {
        const selected = field.options?.find((option) => String(option.value ?? "__all__") === String(value));
        filters[field.key] = selected?.value ?? (value === "__all__" ? null : value);
      }
    }
    onSubmit(filters);
  }

  return <form className="screener-filters" onSubmit={submit}>
    <h2>Filters</h2>
    {fields.map((field) => <fieldset key={field.key} className={field.optional && !enabled[field.key] ? "is-disabled" : ""}>
      {field.optional && <label className="filter-enable"><input type="checkbox" checked={enabled[field.key] ?? false} onChange={(event) => setEnabled({ ...enabled, [field.key]: event.target.checked })} /> Use {field.label}</label>}
      {!field.optional && <legend>{field.label}</legend>}
      {field.type === "number" && <input aria-label={field.label} disabled={field.optional && !enabled[field.key]} type="number" min={field.min} max={field.max} step={field.step ?? 1} value={String(values[field.key] ?? "")} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })} />}
      {field.type === "boolean" && <label className="filter-enable"><input type="checkbox" checked={values[field.key] === true} onChange={(event) => setValues({ ...values, [field.key]: event.target.checked })} /> {field.label}</label>}
      {field.type === "select" && <select aria-label={field.label} value={String(values[field.key] ?? "__all__")} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })}>{field.options?.map((option) => <option key={String(option.value)} value={option.value === null ? "__all__" : String(option.value)}>{option.label}</option>)}</select>}
    </fieldset>)}
    <button type="submit">Apply filters</button>
  </form>;
}

export function SaveScreenResults({ data, onError }: { data: TableResponse; onError: (message: string) => void }) {
  const [name, setName] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  async function save() {
    if (!name.trim()) return onError("Enter a name to save this result set.");
    try {
      await requestJson("watchlists", "POST", { name: name.trim(), tickers: data.rows.map((row) => String(row.ticker)) });
      notifyWatchlistsChanged();
      setSaved(`Saved “${name.trim()}” with ${data.rows.length} members.`);
      setName("");
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : "Unable to save watchlist.");
    }
  }
  return <section className="save-results"><label htmlFor="screen-save-name">Save these results as a watchlist<input id="screen-save-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Screen result" /></label><button type="button" onClick={() => void save()}>Save watchlist</button>{saved && <small role="status">{saved}</small>}</section>;
}
