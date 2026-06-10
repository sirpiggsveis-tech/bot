import { FormEvent, useEffect, useState } from "react";
import { api, PdConfig } from "../api";
import { PageHeader, ErrorBanner } from "../components/ui";
import BotBanner from "../components/BotBanner";
import GuildDirectoryBanner from "../components/GuildDirectoryBanner";
import { useGuild } from "../hooks/useGuild";

export default function PdMode() {
  const { guild } = useGuild();
  const [config, setConfig] = useState<PdConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [lockRole, setLockRole] = useState("");
  const [channelIds, setChannelIds] = useState<number[]>([]);

  async function load() {
    try {
      const c = await api.get<PdConfig>("/api/bot/pd");
      setConfig(c);
      setLockRole(c.lock_role_id ? String(c.lock_role_id) : "");
      setChannelIds(c.channel_ids ?? []);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function toggleChannel(id: number) {
    setChannelIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setMsg(null);
    try {
      await api.put("/api/bot/pd", {
        lock_role_id: lockRole ? Number(lockRole) : null,
        channel_ids: channelIds,
      });
      setMsg("PD config saved.");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function action(path: string, label: string) {
    setError(null);
    setMsg(null);
    try {
      const r = await api.post<Record<string, unknown>>(path);
      setMsg(`${label}: ${JSON.stringify(r)}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <PageHeader
        title="PD mode"
        subtitle="/pdconfig · /pdon · /pdoff · /pdconfigclear"
      />
      <BotBanner />
      <GuildDirectoryBanner guild={guild} />
      <ErrorBanner message={error} />
      {msg && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm">
          {msg}
        </div>
      )}

      {config && (
        <div className="mb-4 card p-4 text-sm">
          Status:{" "}
          <strong className={config.active ? "text-red-400" : "text-green-400"}>
            {config.active ? "ACTIVE" : "off"}
          </strong>
        </div>
      )}

      <form onSubmit={save} className="card mb-6 space-y-4 p-6">
        <div>
          <label className="label">Lock role</label>
          <select className="input" value={lockRole} onChange={(e) => setLockRole(e.target.value)}>
            <option value="">— pick role —</option>
            {guild.roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Channels to lock</label>
          {guild.text_channels.length === 0 ? (
            <p className="text-sm text-amber-300">No channels loaded — run /botpanel sync first.</p>
          ) : (
            <div className="flex max-h-48 flex-wrap gap-2 overflow-y-auto rounded border border-panel-border p-2">
              {guild.text_channels.map((c) => {
                const id = Number(c.id);
                const on = channelIds.includes(id);
                return (
                  <button
                    key={c.id}
                    type="button"
                    className={
                      on
                        ? "rounded-md bg-panel-accent/20 px-2 py-1 text-xs text-panel-accent"
                        : "rounded-md bg-panel-bg px-2 py-1 text-xs text-panel-muted hover:text-white"
                    }
                    onClick={() => toggleChannel(id)}
                  >
                    {c.category ? `${c.category} / ` : ""}
                    {c.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <button type="submit" className="btn-primary">
          Save config
        </button>
      </form>

      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" onClick={() => action("/api/bot/pd/on", "PD ON")}>
          PD ON
        </button>
        <button className="btn-secondary" onClick={() => action("/api/bot/pd/off", "PD OFF")}>
          PD OFF
        </button>
        <button
          className="btn-secondary"
          onClick={async () => {
            setError(null);
            setMsg(null);
            try {
              await api.del("/api/bot/pd");
              setMsg("PD config cleared.");
              await load();
            } catch (err) {
              setError((err as Error).message);
            }
          }}
        >
          Clear config
        </button>
      </div>
    </div>
  );
}
