const TOKEN_KEY = "orbat_panel_token";

/** Live Render service — always call this directly from the browser (CORS allows *.pages.dev). */
export const RENDER_API = "https://orbat-bot.onrender.com";

function resolveApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE as string | undefined;
  if (raw) return raw.replace(/\/$/, "");
  if (import.meta.env.DEV) return "http://localhost:8000";
  return RENDER_API;
}

export const API_BASE = resolveApiBase();

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

const REQUEST_TIMEOUT_MS = 90_000;

function authHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return { ...headers, ...(extra as Record<string, string> | undefined) };
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: authHeaders(options.headers),
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        0,
        "Server took too long to respond. Wait a minute and try again."
      );
    }
    throw new ApiError(0, "Could not reach the server. Check your connection.");
  } finally {
    window.clearTimeout(timer);
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg?: string }) => d.msg).join(", ");
    } catch {
      try {
        const text = await resp.text();
        if (text) detail = text.slice(0, 200);
      } catch {
        /* ignore */
      }
    }
    throw new ApiError(resp.status, detail || "Request failed");
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

export interface LoginResponse {
  ok: boolean;
  user: Me;
  token: string;
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
  nickname: string;
  global_name: string;
  rank: string;
  position: string;
  unit_id: number | null;
  join_date: string;
  active: number;
  note: string;
  rank_locked: number;
  roles: string[];
  role_ids: number[];
  synced_at: string | null;
}

export interface OrbatSettings {
  guild_id: number;
  embed_color: number;
  title: string;
  rank_source: "roles" | "manual";
  auto_sync: number;
  embed_footer: string;
  show_inactive_in_panel: number;
  member_sort_mode: "rank" | "name" | "join";
  roster_show_notes: number;
}

export interface GuildSyncState {
  guild_id: number;
  last_sync_at: string | null;
  last_sync_by: string;
  sync_requested_at: string | null;
  member_count: number;
  channel_count: number;
  role_count: number;
  guild_name: string;
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

export interface BotStatus {
  online: boolean;
  attached: boolean;
}

export interface GuildChannel {
  id: string;
  name: string;
  category?: string | null;
}

export interface GuildRole {
  id: string;
  name: string;
  color: number;
}

export interface GuildMember {
  id: string;
  name: string;
}

export interface GuildDirectory {
  text_channels: GuildChannel[];
  voice_channels: GuildChannel[];
  categories: GuildChannel[];
  roles: GuildRole[];
  members: GuildMember[];
  sync?: GuildSyncState;
  from_cache?: boolean;
  live?: boolean;
  needs_sync?: boolean;
  live_error?: string;
  bot_offline?: boolean;
  message?: string;
}

export interface PdConfig {
  channel_ids: number[];
  lock_role_id: number | null;
  lock_role_ids: number[];
  bypass_role_ids: number[];
  active: boolean;
  saved_permissions: Record<string, unknown>;
}

export interface ReactionTrigger {
  channel_id: number;
  emoji: string;
  role_ids: number[];
}

export interface AutoroleConfig {
  join_roles: number[];
  reaction_triggers: ReactionTrigger[];
  join_nickname: string;
}

export interface SquadConfig {
  staff_role_ids: number[];
  category_id: number | null;
  squads: { channel_id: number; name: string }[];
}

export interface CommandInfo {
  name: string;
  usage: string;
  summary: string;
  access: string;
  panel?: string;
}

export interface CommandCategory {
  category: string;
  commands: CommandInfo[];
}
