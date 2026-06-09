import { NavLink, useNavigate } from "react-router-dom";
import { ReactNode } from "react";
import { useAuth } from "../auth";

interface NavItem {
  to: string;
  label: string;
  group: string;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", group: "Overview" },
  { to: "/commands", label: "All commands", group: "Overview" },
  { to: "/orbat/units", label: "Units", group: "ORBAT" },
  { to: "/orbat/members", label: "Members", group: "ORBAT" },
  { to: "/orbat/ranks", label: "Ranks", group: "ORBAT" },
  { to: "/orbat/positions", label: "Positions", group: "ORBAT" },
  { to: "/orbat/settings", label: "Settings", group: "ORBAT" },
  { to: "/messaging", label: "Messaging", group: "Bot" },
  { to: "/pd-mode", label: "PD mode", group: "Bot" },
  { to: "/auto-roles", label: "Auto-roles", group: "Bot" },
  { to: "/squads", label: "Squads", group: "Bot" },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const groups = Array.from(new Set(NAV.map((n) => n.group)));

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-60 flex-col border-r border-panel-border bg-panel-surface">
        <div className="border-b border-panel-border px-5 py-4">
          <div className="text-lg font-bold tracking-tight">ORBAT</div>
          <div className="text-xs text-panel-muted">Control Panel</div>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {groups.map((group) => (
            <div key={group} className="mb-4">
              <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-widest text-panel-muted">
                {group}
              </div>
              {NAV.filter((n) => n.group === group).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `block rounded-md px-2 py-1.5 text-sm transition-colors ${
                      isActive
                        ? "bg-panel-accent/15 text-panel-accent"
                        : "text-panel-muted hover:bg-panel-bg hover:text-white"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="border-t border-panel-border px-4 py-3">
          <div className="text-sm font-medium">{user?.username}</div>
          <div className="mb-2 text-xs uppercase tracking-wide text-panel-accent">
            {user?.tier}
          </div>
          <button
            className="btn-secondary w-full"
            onClick={async () => {
              await logout();
              navigate("/");
            }}
          >
            Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">{children}</div>
      </main>
    </div>
  );
}
