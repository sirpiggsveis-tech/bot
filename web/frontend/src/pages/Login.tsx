import { FormEvent, useState } from "react";
import { ApiError, RENDER_API } from "../api";
import { useAuth } from "../auth";

async function wakeServer(onStatus: (msg: string) => void): Promise<boolean> {
  const started = Date.now();
  const maxWaitMs = 180_000;
  let attempt = 0;

  while (Date.now() - started < maxWaitMs) {
    attempt += 1;
    const elapsed = Math.round((Date.now() - started) / 1000);
    onStatus(
      attempt === 1
        ? "Waking Render API (free tier sleeps when idle)…"
        : `Still waking Render… ${elapsed}s`
    );

    try {
      const ctrl = new AbortController();
      const timer = window.setTimeout(() => ctrl.abort(), 100_000);
      const r = await fetch(`${RENDER_API}/ping`, {
        cache: "no-store",
        mode: "cors",
        signal: ctrl.signal,
      });
      window.clearTimeout(timer);

      const text = (await r.text()).trim();
      if (r.ok && text === "ok") return true;

      // Cloudflare proxy bug: same-origin /ping can return the SPA HTML with 200.
      if (text.startsWith("<!") || text.startsWith("<html")) {
        throw new ApiError(
          0,
          "Panel is calling the wrong URL (got HTML instead of ok). Remove VITE_API_BASE on Cloudflare and redeploy."
        );
      }
    } catch (err) {
      if (err instanceof ApiError) throw err;
      /* Render cold start — retry */
    }

    await new Promise((r) => setTimeout(r, 2500));
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
          `Render did not respond in 3 minutes. Open ${RENDER_API}/ping in a new tab — if that works, redeploy Cloudflare Pages. If it hangs, check Render → orbat-bot → Logs.`
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
          First sign-in after idle may take 30–90s while Render wakes up.
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
