import { FormEvent, useEffect, useState } from "react";
import { api, AutoroleConfig, ReactionTrigger } from "../api";
import { PageHeader, ErrorBanner } from "../components/ui";
import BotBanner from "../components/BotBanner";
import { useGuild } from "../hooks/useGuild";

export default function AutoRoles() {
  const { guild } = useGuild();
  const [config, setConfig] = useState<AutoroleConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [nickname, setNickname] = useState("");
  const [joinRoles, setJoinRoles] = useState<number[]>([]);
  const [newTrigger, setNewTrigger] = useState({
    channel_id: "",
    emoji: "✅",
    role_ids: [] as number[],
  });

  async function load() {
    const c = await api.get<AutoroleConfig>("/api/bot/autorole");
    setConfig(c);
    setNickname(c.join_nickname || "");
    setJoinRoles(c.join_roles || []);
  }

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
  }, []);

  function toggleRole(id: number) {
    setJoinRoles((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function saveJoin(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.put("/api/bot/autorole", { join_roles: joinRoles, join_nickname: nickname });
      setMsg("Auto-role settings saved.");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function addTrigger(e: FormEvent) {
    e.preventDefault();
    if (!newTrigger.channel_id) return;
    setError(null);
    try {
      await api.post("/api/bot/autorole/reactions", {
        channel_id: Number(newTrigger.channel_id),
        emoji: newTrigger.emoji,
        role_ids: newTrigger.role_ids,
      });
      setMsg("Reaction trigger added.");
      setNewTrigger({ channel_id: "", emoji: "✅", role_ids: [] });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function clearAll() {
    if (!confirm("Clear all auto-role settings?")) return;
    await api.del("/api/bot/autorole");
    setMsg("Cleared.");
    await load();
  }

  async function saveTriggers(triggers: ReactionTrigger[]) {
    await api.put("/api/bot/autorole", { reaction_triggers: triggers });
    await load();
  }

  return (
    <div>
      <PageHeader title="Auto-roles" subtitle="/autoroleconfig — join, reaction, nickname" />
      <BotBanner />
      <ErrorBanner message={error} />
      {msg && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm">
          {msg}
        </div>
      )}

      <form onSubmit={saveJoin} className="card mb-6 space-y-4 p-6">
        <h2 className="text-sm font-semibold uppercase text-panel-muted">Join roles & nickname</h2>
        <div>
          <label className="label">Auto nickname for new members</label>
          <input className="input" value={nickname} onChange={(e) => setNickname(e.target.value)} />
        </div>
        <div>
          <label className="label">Roles on join</label>
          <div className="flex flex-wrap gap-2">
            {guild.roles.map((r) => (
              <label key={r.id} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={joinRoles.includes(Number(r.id))}
                  onChange={() => toggleRole(Number(r.id))}
                />
                {r.name}
              </label>
            ))}
          </div>
        </div>
        <button type="submit" className="btn-primary">
          Save
        </button>
      </form>

      <div className="card mb-6 p-6">
        <h2 className="mb-4 text-sm font-semibold uppercase text-panel-muted">
          Reaction triggers
        </h2>
        {config?.reaction_triggers?.length ? (
          <ul className="mb-4 space-y-2 text-sm">
            {config.reaction_triggers.map((t, i) => (
              <li key={i} className="flex items-center justify-between gap-2">
                <span>
                  ch {t.channel_id} · {t.emoji} → roles {t.role_ids.join(", ")}
                </span>
                <button
                  type="button"
                  className="text-red-400 text-xs"
                  onClick={() =>
                    saveTriggers(config.reaction_triggers.filter((_, j) => j !== i))
                  }
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mb-4 text-sm text-panel-muted">No reaction triggers yet.</p>
        )}

        <form onSubmit={addTrigger} className="grid gap-3 md:grid-cols-4">
          <select
            className="input"
            value={newTrigger.channel_id}
            onChange={(e) => setNewTrigger({ ...newTrigger, channel_id: e.target.value })}
          >
            <option value="">Channel</option>
            {guild.text_channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <input
            className="input"
            value={newTrigger.emoji}
            onChange={(e) => setNewTrigger({ ...newTrigger, emoji: e.target.value })}
            placeholder="Emoji"
          />
          <select
            className="input"
            multiple
            value={newTrigger.role_ids.map(String)}
            onChange={(e) =>
              setNewTrigger({
                ...newTrigger,
                role_ids: Array.from(e.target.selectedOptions).map((o) => Number(o.value)),
              })
            }
          >
            {guild.roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <button type="submit" className="btn-secondary">
            Add trigger
          </button>
        </form>
      </div>

      <button type="button" className="btn-secondary text-red-300" onClick={clearAll}>
        Clear all auto-role settings
      </button>
    </div>
  );
}
