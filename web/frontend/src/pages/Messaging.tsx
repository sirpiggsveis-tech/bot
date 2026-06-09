import { FormEvent, useState } from "react";
import { api } from "../api";
import { PageHeader, ErrorBanner } from "../components/ui";
import BotBanner from "../components/BotBanner";
import { useGuild } from "../hooks/useGuild";

export default function Messaging() {
  const { guild } = useGuild();
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [sayChannel, setSayChannel] = useState("");
  const [sayText, setSayText] = useState("");
  const [voiceChannels, setVoiceChannels] = useState<number[]>([]);
  const [orderText, setOrderText] = useState("");
  const [purgeChannel, setPurgeChannel] = useState("");
  const [purgeAmount, setPurgeAmount] = useState(10);

  async function onSay(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.post("/api/bot/messaging/say", {
        channel_id: Number(sayChannel),
        text: sayText,
      });
      setMsg("Say message sent.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function onOrder(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.post("/api/bot/messaging/order", {
        channel_ids: voiceChannels,
        text: orderText,
      });
      setMsg(`TTS order: ${JSON.stringify(r)}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function onPurge(e: FormEvent) {
    e.preventDefault();
    if (!confirm(`Delete up to ${purgeAmount} messages?`)) return;
    setError(null);
    try {
      const r = await api.post<{ deleted: number }>("/api/bot/messaging/purge", {
        channel_id: Number(purgeChannel),
        amount: purgeAmount,
      });
      setMsg(`Purged ${r.deleted} message(s).`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div>
      <PageHeader title="Messaging" subtitle="/say · /order · /purge" />
      <BotBanner />
      <ErrorBanner message={error} />
      {msg && (
        <div className="mb-4 rounded-md border border-panel-accent/40 bg-panel-accent/10 p-3 text-sm">
          {msg}
        </div>
      )}

      <form onSubmit={onSay} className="card mb-6 space-y-4 p-6">
        <h2 className="text-sm font-semibold uppercase text-panel-muted">/say</h2>
        <select className="input" value={sayChannel} onChange={(e) => setSayChannel(e.target.value)} required>
          <option value="">Text channel</option>
          {guild.text_channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <textarea
          className="input min-h-[120px]"
          value={sayText}
          onChange={(e) => setSayText(e.target.value)}
          placeholder="Message (red embed)"
          required
        />
        <button type="submit" className="btn-primary">
          Send say
        </button>
      </form>

      <form onSubmit={onOrder} className="card mb-6 space-y-4 p-6">
        <h2 className="text-sm font-semibold uppercase text-panel-muted">/order (TTS)</h2>
        <select
          className="input"
          multiple
          value={voiceChannels.map(String)}
          onChange={(e) =>
            setVoiceChannels(
              Array.from(e.target.selectedOptions).map((o) => Number(o.value))
            )
          }
          required
        >
          {guild.voice_channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input
          className="input"
          value={orderText}
          onChange={(e) => setOrderText(e.target.value)}
          placeholder="Spoken text"
          required
        />
        <button type="submit" className="btn-primary">
          Speak in channels
        </button>
      </form>

      <form onSubmit={onPurge} className="card space-y-4 p-6">
        <h2 className="text-sm font-semibold uppercase text-panel-muted">/purge</h2>
        <select
          className="input"
          value={purgeChannel}
          onChange={(e) => setPurgeChannel(e.target.value)}
          required
        >
          <option value="">Text channel</option>
          {guild.text_channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <input
          className="input"
          type="number"
          min={1}
          max={50}
          value={purgeAmount}
          onChange={(e) => setPurgeAmount(Number(e.target.value))}
        />
        <button type="submit" className="btn-secondary">
          Purge messages
        </button>
      </form>
    </div>
  );
}
