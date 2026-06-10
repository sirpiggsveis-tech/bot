import { useEffect, useState } from "react";
import { api, ApiError, BotStatus } from "../api";

type BannerKind = "hidden" | "api_outdated" | "bot_remote";

export default function BotBanner() {
  const [kind, setKind] = useState<BannerKind>("hidden");

  useEffect(() => {
    api
      .get<BotStatus>("/api/bot/status")
      .then((status) => {
        if (status.online) setKind("hidden");
        else setKind("bot_remote");
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setKind("api_outdated");
        else setKind("bot_remote");
      });
  }, []);

  if (kind === "hidden") return null;

  if (kind === "api_outdated") {
    return (
      <div className="mb-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
        The panel API on Render is <strong>out of date</strong> (missing bot routes). In{" "}
        <strong>Render → orbat-bot → Manual Deploy → Deploy latest commit</strong>, wait until
        the deploy finishes, then hard-refresh this page (Ctrl+F5).
      </div>
    );
  }

  return (
    <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
      Your Discord bot runs on <strong>JustRunMy.App</strong>, not on Render — so it can be{" "}
      <strong>green in Discord</strong> while this panel cannot run live actions (say, PD on/off,
      squads, sync). Use <strong>slash commands in Discord</strong> for those. ORBAT and config
      edits here still save to the database.
    </div>
  );
}
