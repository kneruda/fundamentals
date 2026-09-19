export type Column = { key: string; label: string; format: string };
export type TableResponse = { columns: Column[]; rows: Record<string, unknown>[]; total: number; excluded_count: number };

async function requestError(response: Response, fallback: string): Promise<Error> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") return new Error(body.detail);
  } catch { /* The API may return a non-JSON gateway error. */ }
  return new Error(fallback);
}

export async function runFundamentalScreen(screen: string, filters: Record<string, unknown>, watchlistId: number | null = null): Promise<TableResponse> {
  const response = await fetch(`/api/v1/screens/fundamental/${screen}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ filters, watchlist_id: watchlistId })
  });
  if (!response.ok) throw await requestError(response, "Unable to run screen");
  return response.json() as Promise<TableResponse>;
}

export async function getTable(path: string): Promise<TableResponse> {
  const response = await fetch(`/api/v1/${path}`);
  if (!response.ok) throw await requestError(response, "Unable to load data");
  const payload: unknown = await response.json();
  if (Array.isArray(payload)) {
    const rows = payload as Record<string, unknown>[];
    return { columns: Object.keys(rows[0] ?? {}).map(key => ({ key, label: key.replaceAll("_", " "), format: "text" })), rows, total: rows.length, excluded_count: 0 };
  }
  return payload as TableResponse;
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/${path}`);
  if (!response.ok) throw await requestError(response, "Unable to load data");
  return response.json() as Promise<T>;
}

export async function requestJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, { method, headers: { "content-type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw await requestError(response, "Request failed");
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export async function runScreen(family: string, screen: string, filters: Record<string, unknown>, watchlistId: number | null = null): Promise<TableResponse> {
  const response = await fetch(`/api/v1/screens/${family}/${screen}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ filters, watchlist_id: watchlistId }) });
  if (!response.ok) throw await requestError(response, "Unable to run screen");
  return response.json() as Promise<TableResponse>;
}
