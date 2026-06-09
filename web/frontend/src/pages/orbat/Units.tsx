import { useEffect, useState } from "react";
import { api, Unit } from "../../api";
import { PageHeader, ErrorBanner, Modal, Empty } from "../../components/ui";

interface TreeRow {
  unit: Unit;
  depth: number;
}

function buildTree(units: Unit[]): TreeRow[] {
  const byParent = new Map<number | null, Unit[]>();
  units.forEach((u) => {
    const arr = byParent.get(u.parent_id) || [];
    arr.push(u);
    byParent.set(u.parent_id, arr);
  });
  const rows: TreeRow[] = [];
  const walk = (parent: number | null, depth: number) => {
    (byParent.get(parent) || [])
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name))
      .forEach((u) => {
        rows.push({ unit: u, depth });
        walk(u.id, depth + 1);
      });
  };
  walk(null, 0);
  return rows;
}

export default function Units() {
  const [units, setUnits] = useState<Unit[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [editing, setEditing] = useState<Unit | null>(null);

  async function load() {
    try {
      setUnits(await api.get<Unit[]>("/api/orbat/units"));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function remove(unit: Unit) {
    if (!confirm(`Delete "${unit.name}"? Sub-units and members move up to its parent.`))
      return;
    try {
      await api.del(`/api/orbat/units/${unit.id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const rows = buildTree(units);

  return (
    <div>
      <PageHeader
        title="Units"
        subtitle="Build your hierarchy: companies, platoons, squads, teams."
        actions={
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + Add unit
          </button>
        }
      />
      <ErrorBanner message={error} />

      {rows.length === 0 ? (
        <Empty>No units yet. Create your first one to start the tree.</Empty>
      ) : (
        <div className="card divide-y divide-panel-border">
          {rows.map(({ unit, depth }) => (
            <div
              key={unit.id}
              className="flex items-center justify-between px-4 py-3"
              style={{ paddingLeft: 16 + depth * 22 }}
            >
              <div>
                <div className="font-medium">
                  {depth > 0 && <span className="text-panel-muted">↳ </span>}
                  {unit.name}{" "}
                  <span className="text-xs text-panel-muted">#{unit.id}</span>
                </div>
                {unit.description && (
                  <div className="text-xs text-panel-muted">{unit.description}</div>
                )}
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary" onClick={() => setEditing(unit)}>
                  Edit
                </button>
                <button className="btn-danger" onClick={() => remove(unit)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateUnit
          units={units}
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            load();
          }}
        />
      )}
      {editing && (
        <EditUnit
          unit={editing}
          units={units}
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

function CreateUnit({
  units,
  onClose,
  onSaved,
}: {
  units: Unit[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [parent, setParent] = useState<string>("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    try {
      await api.post("/api/orbat/units", {
        name,
        parent_id: parent ? Number(parent) : null,
        description,
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title="Add unit" onClose={onClose}>
      <ErrorBanner message={error} />
      <div className="space-y-4">
        <div>
          <label className="label">Name</label>
          <input
            className="input"
            value={name}
            placeholder='e.g. "1st Platoon" or "dingus team"'
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Parent unit</label>
          <select className="input" value={parent} onChange={(e) => setParent(e.target.value)}>
            <option value="">Top level (no parent)</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label">Description (optional)</label>
          <input
            className="input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={!name.trim()}>
            Create
          </button>
        </div>
      </div>
    </Modal>
  );
}

function EditUnit({
  unit,
  units,
  onClose,
  onSaved,
}: {
  unit: Unit;
  units: Unit[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(unit.name);
  const [description, setDescription] = useState(unit.description);
  const [parent, setParent] = useState<string>(
    unit.parent_id ? String(unit.parent_id) : ""
  );
  const [leader, setLeader] = useState<string>(
    unit.leader_id ? String(unit.leader_id) : ""
  );
  const [error, setError] = useState<string | null>(null);

  async function save() {
    try {
      await api.patch(`/api/orbat/units/${unit.id}`, {
        name,
        description,
        leader_id: leader ? Number(leader) : null,
        clear_leader: !leader,
      });
      const newParent = parent ? Number(parent) : null;
      if (newParent !== unit.parent_id) {
        await api.post(`/api/orbat/units/${unit.id}/move`, { new_parent_id: newParent });
      }
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title={`Edit ${unit.name}`} onClose={onClose}>
      <ErrorBanner message={error} />
      <div className="space-y-4">
        <div>
          <label className="label">Name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label">Description</label>
          <input
            className="input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div>
          <label className="label">Parent unit (move)</label>
          <select className="input" value={parent} onChange={(e) => setParent(e.target.value)}>
            <option value="">Top level (no parent)</option>
            {units
              .filter((u) => u.id !== unit.id)
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
          </select>
        </div>
        <div>
          <label className="label">Leader Discord ID (optional)</label>
          <input
            className="input"
            value={leader}
            placeholder="e.g. 123456789012345678"
            onChange={(e) => setLeader(e.target.value.replace(/\D/g, ""))}
          />
        </div>
        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={!name.trim()}>
            Save
          </button>
        </div>
      </div>
    </Modal>
  );
}
