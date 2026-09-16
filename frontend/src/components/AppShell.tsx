import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Documents" },
  { to: "/findings", label: "Findings" },
  { to: "/audit-log", label: "Audit log" },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <p className="font-display text-xl tracking-tight text-forest">AuditTrace</p>
            <p className="text-sm text-ink/60">Internal document review</p>
          </div>
          <nav className="flex gap-1">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-medium transition-opacity duration-150 ${
                    isActive
                      ? "bg-forest text-paper"
                      : "text-ink/70 hover:bg-paper hover:text-ink active:opacity-70"
                  }`
                }
              >
                {link.label}
              </NavLink>
            ))}
            <a
              href="/api/export.json"
              className="rounded-md px-3 py-2 text-sm font-medium text-ink/70 hover:bg-paper hover:text-ink active:opacity-70"
            >
              Export JSON
            </a>
            <a
              href="/api/export.csv"
              className="rounded-md px-3 py-2 text-sm font-medium text-ink/70 hover:bg-paper hover:text-ink active:opacity-70"
            >
              Export CSV
            </a>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
    </div>
  );
}
