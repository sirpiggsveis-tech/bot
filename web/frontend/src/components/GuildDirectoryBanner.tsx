import { GuildDirectory } from "../api";

export default function GuildDirectoryBanner({ guild }: { guild: GuildDirectory }) {
  if (guild.roles.length > 0 || guild.text_channels.length > 0) return null;

  if (guild.live) return null;

  return (
    <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200">
      {guild.needs_sync ? (
        <>
          Channel and role lists are empty. Run <strong>/botpanel sync</strong> in Discord, or
          click <strong>Sync from Discord</strong> on the Members/Settings page, then refresh
          (Ctrl+F5).
        </>
      ) : (
        <>Could not load server channels/roles. Try syncing from Discord.</>
      )}
      {guild.live_error ? (
        <div className="mt-2 text-xs text-red-300">Live fetch failed: {guild.live_error}</div>
      ) : null}
    </div>
  );
}
