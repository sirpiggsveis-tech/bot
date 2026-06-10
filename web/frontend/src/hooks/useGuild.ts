import { useEffect, useState } from "react";
import { api, GuildDirectory } from "../api";

const EMPTY: GuildDirectory = {
  text_channels: [],
  voice_channels: [],
  categories: [],
  roles: [],
  members: [],
};

export function useGuild() {
  const [guild, setGuild] = useState<GuildDirectory>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await api.get<GuildDirectory>("/api/guild/directory");
        if (!cancelled) setGuild(data);
      } catch {
        try {
          const data = await api.get<GuildDirectory>("/api/bot/guild");
          if (!cancelled) setGuild(data);
        } catch {
          if (!cancelled) setGuild({ ...EMPTY, bot_offline: true, needs_sync: true });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return { guild, loading };
}
