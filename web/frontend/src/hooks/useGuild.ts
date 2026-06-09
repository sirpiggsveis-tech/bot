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
    api
      .get<GuildDirectory>("/api/bot/guild")
      .then(setGuild)
      .catch(() => setGuild({ ...EMPTY, bot_offline: true }))
      .finally(() => setLoading(false));
  }, []);

  return { guild, loading };
}
