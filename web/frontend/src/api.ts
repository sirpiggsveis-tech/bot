export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(
  /\/$/,
  ""
) || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  const text = await resp.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export const loginUrl = `${API_BASE}/api/auth/login`;

// ---- shared types -------------------------------------------------------
export interface Me {
  id: string;
  username: string;
  avatar: string | null;
  tier: "admin" | "staff" | "viewer";
}

export interface Unit {
  id: number;
  name: string;
  parent_id: number | null;
  sort_order: number;
  description: string;
  leader_id: number | null;
}

export interface Rank {
  id: number;
  name: string;
  abbreviation: string;
  sort_order: number;
  role_id: number | null;
}

export interface Position {
  id: number;
  name: string;
  sort_order: number;
}

export interface Member {
  discord_id: number;
  username: string;
  rank: string;
  position: string;
  unit_id: number | null;
  join_date: string;
  active: number;
  note: string;
  rank_locked: number;
  roles: string[];
}

export interface OrbatSettings {
  guild_id: number;
  embed_color: number;
  title: string;
  rank_source: "roles" | "manual";
  auto_sync: number;
}

export interface Overview {
  settings: OrbatSettings;
  counts: {
    members: number;
    active: number;
    units: number;
    ranks: number;
    positions: number;
  };
  units: Unit[];
  ranks: Rank[];
  positions: Position[];
}
