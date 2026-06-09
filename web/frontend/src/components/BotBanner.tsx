import { useEffect, useState } from "react";
import { api, BotStatus } from "../api";

export default function BotBanner() {
  const [status, setStatus] = useState<BotStatus | null>(null);

  useEffect(() => {
    api.get<BotStatus>("/api/bot/status").then(setStatus).catch(() => setStatus({ online: false, attached: false }));
  }, []);

  if (!status || status.online) return null;

  return (
    <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
      Discord bot is offline on the server. Config/ORBAT edits still save, but{" "}
      <strong>say, PD on/off, squads, and sync</strong> need the bot running on{" "}
      <strong>Render Starter</strong> (<code className="text-amber-100">run.py</code>
      , not free tier). See HOSTING_24_7.txt in the repo.
    </div>
  );
}
