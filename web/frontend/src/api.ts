function resolveApiBase(): string {
  // On Cloudflare Pages, always use same-origin /api (proxied to Render in _redirects).
  // This avoids broken login when VITE_API_BASE was set to the Render URL at build time.
  if (typeof window !== "undefined" && window.location.hostname.endsWith(".pages.dev")) {
    return "";
  }

  const raw = import.meta.env.VITE_API_BASE as string | undefined;
  if (raw !== undefined && raw !== "") return raw.replace(/\/$/, "");
  // Vite dev server (port 5173) calls the API on 8000; a built bundle served
  // from the same server uses relative /api/... paths.
  if (import.meta.env.DEV) return "http://localhost:8000";
  return "";
}

export const API_BASE = resolveApiBase();

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const REQUEST_TIMEOUT_MS = 90_000;

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      signal: controller.signal,
      ...options,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        0,
        "Server took too long to respond. On free hosting it may be waking up — wait a minute and try again, or open the Render URL directly."
      );
    }
    throw new ApiError(0, "Could not reach the server. Check your connection and try again.");
  } finally {
    window.clearTimeout(timer);
  }

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

// ---- shared types -------------------------------------------------------
export interface Me {
  id: string;
  username: string;
  avatar: string | null;
  tier: "admin" | "staff" | "viewer";
}

interface LoginResponse {
  ok: boolean;
  user: Me;
}

export type { LoginResponse };

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
