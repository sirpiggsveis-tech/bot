import { useEffect, useState } from "react";
import { api, OrbatSettings } from "../../api";
import { PageHeader, ErrorBanner } from "../../components/ui";
import { useAuth } from "../../auth";

function toHex(n: number) {
  return "#" + n.toString(16).padStart(6, "0").toUpperCase();
}

export default function Settings() {
  const { user } = useAuth();
  const [settings, setSettings] = useState<OrbatSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const isAdmin = user?.tier === "admin";

  async function load() {
    try {
      setSettings(await api.get<OrbatSettings>("/api/orbat/settings"));
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

  if (!settings) return <ErrorBanner message={error} />;

  return (
    <div>
      <PageHeader
        title="ORBAT settings"
        subtitle={
          isAdmin
            ? "Customize how the ORBAT looks and behaves."
            : "Admin access required to change these."
        }
      />
      <ErrorBanner message={error} />
      {saved && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm text-panel-accent">
          Saved.
        </div>
      )}

      <div className="card space-y-5 p-6">
        <div>
          <label className="label">Embed title</label>
          <div className="flex gap-2">
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
              roles = auto from Discord; manual = admins set ranks
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
            <div className="font-medium">Auto-sync</div>
            <div className="text-xs text-panel-muted">
              Sync members on Discord events automatically
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
      </div>
    </div>
  );
}
