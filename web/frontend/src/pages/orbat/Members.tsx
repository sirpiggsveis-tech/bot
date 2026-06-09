import { useEffect, useMemo, useState } from "react";
import { api, Member, Position, Rank, Unit } from "../../api";
import { PageHeader, ErrorBanner, Modal, Empty } from "../../components/ui";

export default function Members() {
  const [members, setMembers] = useState<Member[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [ranks, setRanks] = useState<Rank[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Member | null>(null);

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

  const unitName = (id: number | null) =>
    id ? units.find((u) => u.id === id)?.name ?? "—" : "Unassigned";

  const filtered = useMemo(
    () =>
      members.filter((m) =>
        m.username.toLowerCase().includes(query.toLowerCase())
      ),
    [members, query]
  );

  return (
    <div>
      <PageHeader
        title="Members"
        subtitle="Every tracked member. Data is synced from Discord."
        actions={
          <input
            className="input w-56"
            placeholder="Search…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        }
      />
      <ErrorBanner message={error} />

      {filtered.length === 0 ? (
        <Empty>No members found.</Empty>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-panel-bg text-left text-xs uppercase tracking-wide text-panel-muted">
              <tr>
                <th className="px-4 py-2">Member</th>
                <th className="px-4 py-2">Rank</th>
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
                    <div className="font-medium">{m.username}</div>
                    <div className="text-xs text-panel-muted">{m.discord_id}</div>
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
                    <span
                      className={
                        m.active
                          ? "text-panel-accent"
                          : "text-panel-muted"
                      }
                    >
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
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
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
  onClose,
  onSaved,
}: {
  member: Member;
  units: Unit[];
  ranks: Rank[];
  positions: Position[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [unit, setUnit] = useState(member.unit_id ? String(member.unit_id) : "");
  const [rank, setRank] = useState(member.rank);
  const [position, setPosition] = useState(member.position);
  const [active, setActive] = useState(!!member.active);
  const [note, setNote] = useState(member.note);
  const [error, setError] = useState<string | null>(null);

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
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title={`Edit ${member.username}`} onClose={onClose}>
      <ErrorBanner message={error} />
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
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
            <label className="label">Rank (locks when set)</label>
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
            <label className="label">Status</label>
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
