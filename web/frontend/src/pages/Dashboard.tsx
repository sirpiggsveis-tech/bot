import { useEffect, useState } from "react";
import { api, Overview } from "../api";
import { PageHeader, ErrorBanner } from "../components/ui";
import BotBanner from "../components/BotBanner";
import { useAuth } from "../auth";

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card p-4">
      <div className="text-3xl font-bold">{value}</div>
      <div className="mt-1 text-xs uppercase tracking-wide text-panel-muted">
        {label}
      </div>
    </div>
  );
}

function unitTree(units: Overview["units"]) {
  const byParent = new Map<number | null, Overview["units"]>();
  units.forEach((u) => {
    const arr = byParent.get(u.parent_id) || [];
    arr.push(u);
    byParent.set(u.parent_id, arr);
  });
  const lines: { depth: number; name: string; id: number }[] = [];
  const walk = (parent: number | null, depth: number) => {
    (byParent.get(parent) || [])
      .sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name))
      .forEach((u) => {
        lines.push({ depth, name: u.name, id: u.id });
        walk(u.id, depth + 1);
      });
  };
  walk(null, 0);
  return lines;
}

export default function Dashboard() {
  const { user } = useAuth();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  async function load() {
    try {
      setData(await api.get<Overview>("/api/orbat/overview"));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function sync() {
    setSyncing(true);
    setError(null);
    try {
      await api.post("/api/orbat/sync");
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  const tree = data ? unitTree(data.units) : [];

  return (
    <div>
      <PageHeader
        title={`Welcome, ${user?.username}`}
        subtitle="Live snapshot of the order of battle."
        actions={
          <button className="btn-primary" onClick={sync} disabled={syncing}>
            {syncing ? "Syncing…" : "Sync from Discord"}
          </button>
        }
      />
      <BotBanner />
      <ErrorBanner message={error} />

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            <Stat label="Members" value={data.counts.members} />
            <Stat label="Active" value={data.counts.active} />
            <Stat label="Units" value={data.counts.units} />
            <Stat label="Ranks" value={data.counts.ranks} />
            <Stat label="Positions" value={data.counts.positions} />
          </div>

          <div className="mt-6 card p-5">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-panel-muted">
              Unit tree
            </h2>
            {tree.length === 0 ? (
              <p className="text-sm text-panel-muted">No units yet.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {tree.map((t) => (
                  <li key={t.id} style={{ paddingLeft: t.depth * 18 }}>
                    <span className="text-panel-accent">▸</span> {t.name}{" "}
                    <span className="text-xs text-panel-muted">#{t.id}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </div>
  );
}
