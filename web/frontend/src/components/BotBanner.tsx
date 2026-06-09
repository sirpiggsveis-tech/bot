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
      Discord bot is offline — config saves to the database, but{" "}
      <strong>PD on/off, say, squads, and sync</strong> need{" "}
      <code className="text-amber-100">start-bot.bat</code> running on your PC.
    </div>
  );
}
