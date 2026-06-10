import { useEffect, useMemo, useState } from "react";
import { api, Member, Position, Rank, Unit } from "../../api";
import { PageHeader, ErrorBanner, Modal, Empty } from "../../components/ui";
import { useGuild } from "../../hooks/useGuild";

type FilterMode = "all" | "active" | "inactive";

function displayName(m: Member) {
  return m.nickname || m.global_name || m.username;
}

export default function Members() {
  const { guild } = useGuild();
  const [members, setMembers] = useState<Member[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [ranks, setRanks] = useState<Rank[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<FilterMode>("all");
  const [editing, setEditing] = useState<Member | null>(null);
  const [syncing, setSyncing] = useState(false);

  async function load() {
    try {
      const [m, u, r, p] = await Promise.all([
        api.get<Member[]>("/api/orbat/members"),
        api.get<Unit[]>("/api/orbat/units"),
        api.get<Rank[]>("/api/orbat/ranks"),
        api.get<Position[]>("/api/orbat/positions"),
      ]);
      setMembers(m);
      setUnits(u);
      setRanks(r);
      setPositions(p);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function requestSync() {
    setSyncing(true);
    setError(null);
    setMsg(null);
    try {
      const r = await api.post<{ message?: string; queued?: boolean }>("/api/orbat/sync");
      setMsg(r.message ?? "Sync requested.");
      setTimeout(load, 25000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  const unitName = (id: number | null) =>
    id ? units.find((u) => u.id === id)?.name ?? "—" : "Unassigned";

  const filtered = useMemo(() => {
    let list = members;
    if (filter === "active") list = list.filter((m) => m.active);
    if (filter === "inactive") list = list.filter((m) => !m.active);
    if (query.trim()) {
      const q = query.toLowerCase();
      list = list.filter(
        (m) =>
          displayName(m).toLowerCase().includes(q) ||
          m.username.toLowerCase().includes(q) ||
          String(m.discord_id).includes(q) ||
          m.roles.some((r) => r.toLowerCase().includes(q))
      );
    }
    return list;
  }, [members, query, filter]);

  const syncInfo = guild.sync;

  return (
    <div>
      <PageHeader
        title="Members"
        subtitle="Full server roster from the database. Run /botpanel sync in Discord after big changes."
        actions={
          <div className="flex flex-wrap gap-2">
            <input
              className="input w-44"
              placeholder="Search…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <select
              className="input w-32"
              value={filter}
              onChange={(e) => setFilter(e.target.value as FilterMode)}
            >
              <option value="all">All</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <button className="btn-primary" onClick={requestSync} disabled={syncing}>
              {syncing ? "Queuing…" : "Sync from Discord"}
            </button>
          </div>
        }
      />

      {syncInfo?.last_sync_at ? (
        <div className="mb-4 rounded-md border border-panel-border bg-panel-surface p-3 text-sm text-panel-muted">
          Last sync: <strong className="text-white">{syncInfo.last_sync_at}</strong>
          {syncInfo.guild_name ? ` · ${syncInfo.guild_name}` : ""}
          {" · "}
          {syncInfo.member_count} members, {syncInfo.channel_count} channels,{" "}
          {syncInfo.role_count} roles
          {syncInfo.sync_requested_at ? (
            <span className="text-amber-300"> · Sync pending…</span>
          ) : null}
        </div>
      ) : (
        <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
          No sync data yet. Run <strong>/botpanel sync</strong> in Discord, then refresh.
        </div>
      )}

      <ErrorBanner message={error} />
      {msg && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm">
          {msg}
        </div>
      )}

      {filtered.length === 0 ? (
        <Empty>No members found.</Empty>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-panel-bg text-left text-xs uppercase tracking-wide text-panel-muted">
              <tr>
                <th className="px-4 py-2">Member</th>
                <th className="px-4 py-2">Discord roles</th>
                <th className="px-4 py-2">ORBAT rank</th>
                <th className="px-4 py-2">Position</th>
                <th className="px-4 py-2">Unit</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-panel-border">
              {filtered.map((m) => (
                <tr key={m.discord_id} className="hover:bg-panel-bg/40">
                  <td className="px-4 py-2">
                    <div className="font-medium">{displayName(m)}</div>
                    <div className="text-xs text-panel-muted">
                      @{m.username}
                      {m.nickname && m.nickname !== m.username ? ` · nick: ${m.nickname}` : ""}
                    </div>
                    <div className="text-xs text-panel-muted">{m.discord_id}</div>
                  </td>
                  <td className="px-4 py-2">
                    <div className="flex max-w-xs flex-wrap gap-1">
                      {m.roles.length ? (
                        m.roles.map((r) => (
                          <span
                            key={r}
                            className="rounded bg-panel-bg px-1.5 py-0.5 text-xs text-panel-muted"
                          >
                            {r}
                          </span>
                        ))
                      ) : (
                        <span className="text-panel-muted">—</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    {m.rank || "—"}
                    {m.rank_locked ? (
                      <span className="ml-1 text-xs text-panel-accent">🔒</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2">{m.position || "—"}</td>
                  <td className="px-4 py-2">{unitName(m.unit_id)}</td>
                  <td className="px-4 py-2">
                    <span className={m.active ? "text-panel-accent" : "text-panel-muted"}>
                      {m.active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button className="btn-secondary" onClick={() => setEditing(m)}>
                      Edit
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <EditMember
          member={editing}
          units={units}
          ranks={ranks}
          positions={positions}
          guildRoles={guild.roles}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setMsg("Saved. Discord nickname/role changes apply within ~20s.");
            load();
          }}
        />
      )}
    </div>
  );
}

function EditMember({
  member,
  units,
  ranks,
  positions,
  guildRoles,
  onClose,
  onSaved,
}: {
  member: Member;
  units: Unit[];
  ranks: Rank[];
  positions: Position[];
  guildRoles: { id: string; name: string; color: number }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [unit, setUnit] = useState(member.unit_id ? String(member.unit_id) : "");
  const [rank, setRank] = useState(member.rank);
  const [position, setPosition] = useState(member.position);
  const [active, setActive] = useState(!!member.active);
  const [note, setNote] = useState(member.note);
  const [nickname, setNickname] = useState(member.nickname || "");
  const [roleIds, setRoleIds] = useState<number[]>(member.role_ids ?? []);
  const [error, setError] = useState<string | null>(null);

  function toggleRole(id: number) {
    setRoleIds((prev) =>
      prev.includes(id) ? prev.filter((r) => r !== id) : [...prev, id]
    );
  }

  async function save() {
    try {
      await api.patch(`/api/orbat/members/${member.discord_id}`, {
        unit_id: unit ? Number(unit) : null,
        clear_unit: !unit,
        rank,
        lock_rank: rank !== "",
        position,
        active,
        note,
        nickname: nickname.trim(),
        clear_nickname: !nickname.trim(),
        role_ids: roleIds,
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title={`Edit ${displayName(member)}`} onClose={onClose}>
      <ErrorBanner message={error} />
      <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-1">
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="label">Discord nickname</label>
            <input
              className="input"
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              placeholder={member.username}
              maxLength={32}
            />
            <p className="mt-1 text-xs text-panel-muted">
              Applied on Discord by the bot (~20s). Clear the field to reset nickname.
            </p>
          </div>

          <div className="col-span-2">
            <label className="label">Discord roles</label>
            {guildRoles.length === 0 ? (
              <p className="text-sm text-amber-300">
                No roles cached — run /botpanel sync first.
              </p>
            ) : (
              <div className="flex max-h-40 flex-wrap gap-2 overflow-y-auto rounded border border-panel-border p-2">
                {guildRoles.map((r) => {
                  const id = Number(r.id);
                  const on = roleIds.includes(id);
                  return (
                    <button
                      key={r.id}
                      type="button"
                      className={
                        on
                          ? "rounded-md bg-panel-accent/20 px-2 py-1 text-xs text-panel-accent"
                          : "rounded-md bg-panel-bg px-2 py-1 text-xs text-panel-muted hover:text-white"
                      }
                      onClick={() => toggleRole(id)}
                    >
                      {r.name}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            <label className="label">Unit</label>
            <select className="input" value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option value="">Unassigned</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">ORBAT rank (locks when set)</label>
            <select className="input" value={rank} onChange={(e) => setRank(e.target.value)}>
              <option value="">Clear / auto</option>
              {ranks.map((r) => (
                <option key={r.id} value={r.name}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Position</label>
            <select
              className="input"
              value={position}
              onChange={(e) => setPosition(e.target.value)}
            >
              <option value="">None</option>
              {positions.map((p) => (
                <option key={p.id} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">ORBAT status</label>
            <button
              className={active ? "btn-primary w-full" : "btn-secondary w-full"}
              onClick={() => setActive((a) => !a)}
            >
              {active ? "Active" : "Inactive"}
            </button>
          </div>
        </div>
        <div>
          <label className="label">Note</label>
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save}>
            Save
          </button>
        </div>
      </div>
    </Modal>
  );
}
