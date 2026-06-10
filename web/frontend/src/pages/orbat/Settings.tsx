import { useEffect, useState } from "react";
import { api, GuildSyncState, OrbatSettings } from "../../api";
import { PageHeader, ErrorBanner } from "../../components/ui";
import { useAuth } from "../../auth";

function toHex(n: number) {
  return "#" + n.toString(16).padStart(6, "0").toUpperCase();
}

export default function Settings() {
  const { user } = useAuth();
  const [settings, setSettings] = useState<OrbatSettings | null>(null);
  const [syncState, setSyncState] = useState<GuildSyncState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  const isAdmin = user?.tier === "admin";

  async function load() {
    try {
      const [s, sync] = await Promise.all([
        api.get<OrbatSettings>("/api/orbat/settings"),
        api.get<GuildSyncState>("/api/guild/sync-status"),
      ]);
      setSettings(s);
      setSyncState(sync);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function save(patch: Record<string, string | number | boolean>) {
    setError(null);
    setSaved(false);
    try {
      await api.patch("/api/orbat/settings", patch);
      setSaved(true);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function requestSync() {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const r = await api.post<{ message?: string }>("/api/orbat/sync");
      setSyncMsg(r.message ?? "Sync queued.");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  if (!settings) return <ErrorBanner message={error} />;

  return (
    <div>
      <PageHeader
        title="ORBAT settings"
        subtitle={
          isAdmin
            ? "Panel behavior, display options, and Discord database sync."
            : "Admin access required to change these."
        }
        actions={
          isAdmin ? (
            <button className="btn-primary" onClick={requestSync} disabled={syncing}>
              {syncing ? "Queuing…" : "Sync from Discord"}
            </button>
          ) : undefined
        }
      />
      <ErrorBanner message={error} />
      {saved && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm text-panel-accent">
          Saved.
        </div>
      )}
      {syncMsg && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm">
          {syncMsg}
        </div>
      )}

      <div className="card mb-6 space-y-4 p-6">
        <h2 className="text-sm font-semibold uppercase text-panel-muted">Database sync</h2>
        <p className="text-sm text-panel-muted">
          <strong>/botpanel sync</strong> in Discord (or the button above) copies channels,
          roles, and every member into Supabase. The panel and bot read from that database.
        </p>
        {syncState?.last_sync_at ? (
          <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-panel-muted">Last sync</dt>
              <dd>{syncState.last_sync_at}</dd>
            </div>
            <div>
              <dt className="text-panel-muted">Members</dt>
              <dd>{syncState.member_count}</dd>
            </div>
            <div>
              <dt className="text-panel-muted">Channels</dt>
              <dd>{syncState.channel_count}</dd>
            </div>
            <div>
              <dt className="text-panel-muted">Roles</dt>
              <dd>{syncState.role_count}</dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-amber-300">No sync yet — run /botpanel sync in Discord.</p>
        )}
      </div>

      <div className="card space-y-5 p-6">
        <div>
          <label className="label">Embed title</label>
          <input
            className="input"
            defaultValue={settings.title}
            disabled={!isAdmin}
            onBlur={(e) =>
              isAdmin && e.target.value !== settings.title && save({ title: e.target.value })
            }
            placeholder="Default: ORBAT — <server>"
          />
        </div>

        <div>
          <label className="label">Embed footer</label>
          <input
            className="input"
            defaultValue={settings.embed_footer ?? ""}
            disabled={!isAdmin}
            onBlur={(e) =>
              isAdmin &&
              e.target.value !== (settings.embed_footer ?? "") &&
              save({ embed_footer: e.target.value })
            }
            placeholder="Optional footer text on ORBAT embeds"
          />
        </div>

        <div>
          <label className="label">Embed color</label>
          <div className="flex items-center gap-3">
            <input
              type="color"
              className="h-10 w-16 rounded border border-panel-border bg-panel-bg"
              defaultValue={toHex(settings.embed_color)}
              disabled={!isAdmin}
              onChange={(e) =>
                isAdmin && save({ embed_color: parseInt(e.target.value.slice(1), 16) })
              }
            />
            <span className="text-sm text-panel-muted">{toHex(settings.embed_color)}</span>
          </div>
        </div>

        <div className="flex items-center justify-between border-t border-panel-border pt-4">
          <div>
            <div className="font-medium">Rank source</div>
            <div className="text-xs text-panel-muted">
              roles = auto from Discord; manual = admins set ranks in panel
            </div>
          </div>
          <button
            className="btn-secondary"
            disabled={!isAdmin}
            onClick={() =>
              save({
                rank_source: settings.rank_source === "roles" ? "manual" : "roles",
              })
            }
          >
            {settings.rank_source}
          </button>
        </div>

        <div className="flex items-center justify-between border-t border-panel-border pt-4">
          <div>
            <div className="font-medium">Auto-sync on bot events</div>
            <div className="text-xs text-panel-muted">
              Update database when members join or roles change
            </div>
          </div>
          <button
            className={settings.auto_sync ? "btn-primary" : "btn-secondary"}
            disabled={!isAdmin}
            onClick={() => save({ auto_sync: !settings.auto_sync })}
          >
            {settings.auto_sync ? "On" : "Off"}
          </button>
        </div>

        <div className="flex items-center justify-between border-t border-panel-border pt-4">
          <div>
            <div className="font-medium">Show inactive members in panel</div>
          </div>
          <button
            className={settings.show_inactive_in_panel ? "btn-primary" : "btn-secondary"}
            disabled={!isAdmin}
            onClick={() => save({ show_inactive_in_panel: !settings.show_inactive_in_panel })}
          >
            {settings.show_inactive_in_panel ? "On" : "Off"}
          </button>
        </div>

        <div className="flex items-center justify-between border-t border-panel-border pt-4">
          <div>
            <div className="font-medium">Member list default sort</div>
          </div>
          <select
            className="input w-36"
            disabled={!isAdmin}
            value={settings.member_sort_mode ?? "rank"}
            onChange={(e) => save({ member_sort_mode: e.target.value })}
          >
            <option value="rank">By rank</option>
            <option value="name">By name</option>
            <option value="join">By join date</option>
          </select>
        </div>

        <div className="flex items-center justify-between border-t border-panel-border pt-4">
          <div>
            <div className="font-medium">Show notes on ORBAT cards</div>
          </div>
          <button
            className={settings.roster_show_notes ? "btn-primary" : "btn-secondary"}
            disabled={!isAdmin}
            onClick={() => save({ roster_show_notes: !settings.roster_show_notes })}
          >
            {settings.roster_show_notes ? "On" : "Off"}
          </button>
        </div>
      </div>
    </div>
  );
}
