import { FormEvent, useEffect, useState } from "react";
import { api, SquadConfig } from "../api";
import { PageHeader, ErrorBanner } from "../components/ui";
import BotBanner from "../components/BotBanner";
import { useGuild } from "../hooks/useGuild";

export default function Squads() {
  const { guild } = useGuild();
  const [config, setConfig] = useState<SquadConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [categoryId, setCategoryId] = useState("");
  const [staffRoles, setStaffRoles] = useState<number[]>([]);
  const [squadName, setSquadName] = useState("");
  const [squadMembers, setSquadMembers] = useState<number[]>([]);

  async function load() {
    const c = await api.get<SquadConfig>("/api/bot/squads");
    setConfig(c);
    setCategoryId(c.category_id ? String(c.category_id) : "");
    setStaffRoles(c.staff_role_ids || []);
  }

  useEffect(() => {
    load().catch((e) => setError((e as Error).message));
  }, []);

  async function saveConfig(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.put("/api/bot/squads/config", {
        category_id: categoryId ? Number(categoryId) : null,
        staff_role_ids: staffRoles,
      });
      setMsg("Squad config saved.");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function createSquad(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.post("/api/bot/squads", {
        name: squadName,
        member_ids: squadMembers,
      });
      setMsg(`Squad created: ${JSON.stringify(r)}`);
      setSquadName("");
      setSquadMembers([]);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function deleteSquad(channelId: number) {
    if (!confirm("Delete this squad channel?")) return;
    setError(null);
    try {
      await api.del(`/api/bot/squads/${channelId}`);
      setMsg("Squad deleted.");
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <PageHeader title="Squads" subtitle="/squadconfig · /squadcreate · /squaddelete" />
      <BotBanner />
      <ErrorBanner message={error} />
      {msg && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm">
          {msg}
        </div>
      )}

      <form onSubmit={saveConfig} className="card mb-6 space-y-4 p-6">
        <h2 className="text-sm font-semibold uppercase text-panel-muted">Squad config</h2>
        <div>
          <label className="label">Category for squad VCs</label>
          <select className="input" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">Top level</option>
            {guild.categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Staff roles (see all squads)</label>
          <div className="flex flex-wrap gap-2">
            {guild.roles.map((r) => (
              <label key={r.id} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={staffRoles.includes(Number(r.id))}
                  onChange={() =>
                    setStaffRoles((prev) =>
                      prev.includes(Number(r.id))
                        ? prev.filter((x) => x !== Number(r.id))
                        : [...prev, Number(r.id)]
                    )
                  }
                />
                {r.name}
              </label>
            ))}
          </div>
        </div>
        <button type="submit" className="btn-primary">
          Save config
        </button>
      </form>

      <form onSubmit={createSquad} className="card mb-6 space-y-4 p-6">
        <h2 className="text-sm font-semibold uppercase text-panel-muted">Create squad</h2>
        <input
          className="input"
          placeholder="Squad name"
          value={squadName}
          onChange={(e) => setSquadName(e.target.value)}
          required
        />
        <select
          className="input"
          multiple
          value={squadMembers.map(String)}
          onChange={(e) =>
            setSquadMembers(
              Array.from(e.target.selectedOptions).map((o) => Number(o.value))
            )
          }
        >
          {guild.members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </select>
        <button type="submit" className="btn-primary">
          Create squad VC
        </button>
      </form>

      <div className="card p-6">
        <h2 className="mb-3 text-sm font-semibold uppercase text-panel-muted">Active squads</h2>
        {!config?.squads?.length ? (
          <p className="text-sm text-panel-muted">No squads tracked.</p>
        ) : (
          <ul className="space-y-2">
            {config.squads.map((s) => (
              <li key={s.channel_id} className="flex justify-between text-sm">
                <span>
                  {s.name} <span className="text-panel-muted">#{s.channel_id}</span>
                </span>
                <button
                  type="button"
                  className="text-red-400"
                  onClick={() => deleteSquad(s.channel_id)}
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
