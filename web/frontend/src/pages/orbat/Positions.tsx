import { useEffect, useState } from "react";
import { api, Position } from "../../api";
import { PageHeader, ErrorBanner, Empty } from "../../components/ui";

export default function Positions() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");

  async function load() {
    try {
      setPositions(await api.get<Position[]>("/api/orbat/positions"));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function add() {
    if (!name.trim()) return;
    try {
      await api.post("/api/orbat/positions", { name });
      setName("");
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(p: Position) {
    if (!confirm(`Remove position "${p.name}"?`)) return;
    try {
      await api.del(`/api/orbat/positions/${p.id}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div>
      <PageHeader
        title="Positions"
        subtitle="Billets like Squad Leader, Rifleman, Medic."
      />
      <ErrorBanner message={error} />

      <div className="card mb-6 flex gap-2 p-4">
        <input
          className="input"
          placeholder="New position name…"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <button className="btn-primary" onClick={add} disabled={!name.trim()}>
          Add
        </button>
      </div>

      {positions.length === 0 ? (
        <Empty>No positions yet.</Empty>
      ) : (
        <div className="card divide-y divide-panel-border">
          {positions.map((p) => (
            <div key={p.id} className="flex items-center justify-between px-4 py-3">
              <span className="font-medium">{p.name}</span>
              <button className="btn-danger" onClick={() => remove(p)}>
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
