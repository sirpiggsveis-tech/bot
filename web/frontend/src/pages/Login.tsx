import { useEffect, useState } from "react";
import { loginUrl } from "../api";

export default function Login() {
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("error") === "forbidden") setForbidden(true);
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="card w-full max-w-md p-8 text-center">
        <h1 className="text-2xl font-bold tracking-tight">ORBAT Control Panel</h1>
        <p className="mt-2 text-sm text-panel-muted">
          Sign in with Discord to manage the order of battle and bot configuration.
        </p>

        {forbidden && (
          <div className="mt-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
            Your Discord account does not have access to this panel. Ask an admin to
            grant your role.
          </div>
        )}

        <a href={loginUrl} className="btn-primary mt-6 w-full">
          Login with Discord
        </a>
      </div>
    </div>
  );
}
