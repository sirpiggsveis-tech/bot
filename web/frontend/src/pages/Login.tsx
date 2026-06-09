import { FormEvent, useState } from "react";
import { API_BASE, ApiError } from "../api";
import { useAuth } from "../auth";

async function wakeServer(onStatus: (msg: string) => void): Promise<boolean> {
  const deadline = Date.now() + 120_000;
  let attempt = 0;
  while (Date.now() < deadline) {
    attempt += 1;
    const elapsed = Math.round((Date.now() - (deadline - 120_000)) / 1000);
    onStatus(
      attempt === 1
        ? "Waking server (free tier sleeps when idle)…"
        : `Still waking server… ${elapsed}s`
    );
    try {
      const ctrl = new AbortController();
      const timer = window.setTimeout(() => ctrl.abort(), 25_000);
      const r = await fetch(`${API_BASE}/ping`, {
        cache: "no-store",
        signal: ctrl.signal,
      });
      window.clearTimeout(timer);
      if (r.ok) {
        const text = (await r.text()).trim();
        if (text === "ok") return true;
      }
    } catch {
      /* cold start — retry */
    }
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setStatus("Connecting to server…");
    try {
      const up = await wakeServer(setStatus);
      if (!up) {
        throw new ApiError(
          0,
          "Server did not respond in 2 minutes. In Render dashboard: open orbat-bot → Logs (crash loop?) → Manual Deploy. Or run start-panel.bat locally at http://localhost:8000/"
        );
      }
      setStatus("Signing in…");
      await login(username.trim(), password);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Login failed. Try again."
      );
    } finally {
      setSubmitting(false);
      setStatus(null);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="card w-full max-w-md p-8">
        <h1 className="text-center text-2xl font-bold tracking-tight">
          ORBAT Control Panel
        </h1>
        <p className="mt-2 text-center text-sm text-panel-muted">
          Sign in to manage the order of battle and bot configuration.
        </p>
        <p className="mt-1 text-center text-xs text-panel-muted">
          Free hosting sleeps when idle — sign-in may take 30–60s the first time.
        </p>

        <form onSubmit={onSubmit} className="mt-6 space-y-4 text-left">
          <div>
            <label className="label" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              className="input"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <div className="rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn-primary w-full"
            disabled={submitting}
          >
            {status || (submitting ? "Signing in…" : "Sign in")}
          </button>
        </form>
      </div>
    </div>
  );
}
