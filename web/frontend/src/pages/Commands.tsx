import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, CommandCategory } from "../api";
import { PageHeader, ErrorBanner } from "../components/ui";
import BotBanner from "../components/BotBanner";

export default function Commands() {
  const [categories, setCategories] = useState<CommandCategory[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<{ categories: CommandCategory[] }>("/api/bot/commands")
      .then((r) => setCategories(r.categories))
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div>
      <PageHeader
        title="Bot commands"
        subtitle="Every slash command and where to control it in this panel."
      />
      <BotBanner />
      <ErrorBanner message={error} />

      <div className="space-y-6">
        {categories.map((cat) => (
          <section key={cat.category} className="card p-5">
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-panel-accent">
              {cat.category}
            </h2>
            <div className="space-y-4">
              {cat.commands.map((cmd) => (
                <div
                  key={cmd.name}
                  className="border-b border-panel-border pb-4 last:border-0 last:pb-0"
                >
                  <div className="font-mono text-sm text-white">{cmd.usage}</div>
                  <p className="mt-1 text-sm text-panel-muted">{cmd.summary}</p>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs">
                    <span className="text-panel-muted">Access: {cmd.access}</span>
                    {cmd.panel && (
                      <Link
                        to={cmd.panel}
                        className="text-panel-accent hover:underline"
                      >
                        Open in panel →
                      </Link>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
