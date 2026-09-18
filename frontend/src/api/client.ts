export type Column = { key: string; label: string; format: string };
export type TableResponse = { columns: Column[]; rows: Record<string, unknown>[]; total: number; excluded_count: number };

export async function runFundamentalScreen(screen: string, filters: Record<string, unknown>): Promise<TableResponse> {
  const response = await fetch(`/api/v1/screens/fundamental/${screen}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ filters })
  });
  if (!response.ok) throw new Error((await response.json()).detail ?? "Unable to run screen");
  return response.json() as Promise<TableResponse>;
}

export async function getTable(path: string): Promise<TableResponse> {
  const response = await fetch(`/api/v1/${path}`);
  if (!response.ok) throw new Error("Unable to load data");
  return response.json() as Promise<TableResponse>;
}

export async function runScreen(family: string, screen: string, filters: Record<string, unknown>): Promise<TableResponse> {
  const response = await fetch(`/api/v1/screens/${family}/${screen}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ filters }) });
  if (!response.ok) throw new Error((await response.json()).detail ?? "Unable to run screen");
  return response.json() as Promise<TableResponse>;
}
