import { useEffect, useState } from "react";
import { api, Rank } from "../../api";
import { PageHeader, ErrorBanner, Modal, Empty } from "../../components/ui";

export default function Ranks() {
  const [ranks, setRanks] = useState<Rank[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  async function load() {
    try {
      setRanks(await api.get<Rank[]>("/api/orbat/ranks"));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function remove(rank: Rank) {
    if (!confirm(`Remove rank "${rank.name}"?`)) return;
    try {
      await api.del(`/api/orbat/ranks/${rank.id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function setRole(rank: Rank) {
    const value = prompt(
      `Map "${rank.name}" to a Discord role ID (blank to clear):`,
      rank.role_id ? String(rank.role_id) : ""
    );
    if (value === null) return;
    try {
      await api.put(`/api/orbat/ranks/${rank.id}/role`, {
        role_id: value.trim() ? Number(value.trim()) : null,
      });
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <PageHeader
        title="Ranks"
        subtitle="Higher priority = more senior. Map a rank to a Discord role for auto-detection."
        actions={
          <button className="btn-primary" onClick={() => setShowCreate(true)}>
            + Add rank
          </button>
        }
      />
      <ErrorBanner message={error} />

      {ranks.length === 0 ? (
        <Empty>No ranks yet.</Empty>
      ) : (
        <div className="card divide-y divide-panel-border">
          {ranks.map((r) => (
            <div key={r.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <div className="font-medium">
                  {r.name}
                  {r.abbreviation && (
                    <span className="ml-2 rounded bg-panel-bg px-1.5 py-0.5 text-xs text-panel-muted">
                      {r.abbreviation}
                    </span>
                  )}
                </div>
                <div className="text-xs text-panel-muted">
                  priority {r.sort_order}
                  {r.role_id ? ` · role ${r.role_id}` : " · no role mapping"}
                </div>
              </div>
              <div className="flex gap-2">
                <button className="btn-secondary" onClick={() => setRole(r)}>
                  Map role
                </button>
                <button className="btn-danger" onClick={() => remove(r)}>
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateRank
          onClose={() => setShowCreate(false)}
          onSaved={() => {
            setShowCreate(false);
            load();
          }}
        />
      )}
    </div>
  );
}

function CreateRank({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [abbreviation, setAbbreviation] = useState("");
  const [priority, setPriority] = useState("");
  const [roleId, setRoleId] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    try {
      await api.post("/api/orbat/ranks", {
        name,
        abbreviation,
        sort_order: priority ? Number(priority) : null,
        role_id: roleId ? Number(roleId) : null,
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Modal title="Add rank" onClose={onClose}>
      <ErrorBanner message={error} />
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Name</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="label">Abbreviation</label>
            <input
              className="input"
              value={abbreviation}
              onChange={(e) => setAbbreviation(e.target.value)}
            />
          </div>
          <div>
            <label className="label">Priority (higher = senior)</label>
            <input
              className="input"
              value={priority}
              onChange={(e) => setPriority(e.target.value.replace(/[^\d-]/g, ""))}
            />
          </div>
          <div>
            <label className="label">Discord role ID (optional)</label>
            <input
              className="input"
              value={roleId}
              onChange={(e) => setRoleId(e.target.value.replace(/\D/g, ""))}
            />
          </div>
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
