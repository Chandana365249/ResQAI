import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { Activity, BarChart3, ClipboardList, Menu, ServerCog, ShieldCheck, Truck, X } from "lucide-react";
import { SystemStatusPill } from "../status/SystemStatusPill";

const NAV_ITEMS = [
  { to: "/analyze", label: "Analyze Incident", Icon: ClipboardList },
  { to: "/resources", label: "Resources", Icon: Truck },
  { to: "/analytics", label: "Analytics", Icon: BarChart3 },
  { to: "/system", label: "System", Icon: ServerCog },
];

export function HumanOversightNotice() {
  return (
    <p className="inline-flex items-center gap-1.5 rounded-md bg-teal-50 px-2 py-1 text-xs font-medium text-teal-900 ring-1 ring-inset ring-teal-200">
      <ShieldCheck aria-hidden className="size-3.5 shrink-0" />
      Human oversight required
    </p>
  );
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? "bg-teal-700 text-white" : "text-slate-700 hover:bg-slate-100"
  }`;
}

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  // Close the mobile menu after navigating.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:shadow"
      >
        Skip to main content
      </a>

      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <span aria-hidden className="grid size-9 place-items-center rounded-lg bg-teal-700 text-white">
              <Activity className="size-5" />
            </span>
            <div className="leading-tight">
              <p className="text-lg font-bold tracking-tight text-slate-900">ResQAI</p>
              <p className="text-xs text-slate-600">AI-assisted emergency response · decision-support prototype</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <SystemStatusPill />
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm font-medium text-slate-800 md:hidden"
              aria-expanded={menuOpen}
              aria-controls="primary-nav"
              onClick={() => setMenuOpen((open) => !open)}
            >
              {menuOpen ? <X aria-hidden className="size-4" /> : <Menu aria-hidden className="size-4" />}
              Menu
            </button>
          </div>
        </div>

        <nav
          id="primary-nav"
          aria-label="Primary"
          className={`border-t border-slate-100 ${menuOpen ? "block" : "hidden"} md:block`}
        >
          <ul className="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-2 sm:px-6 md:flex-row">
            {NAV_ITEMS.map(({ to, label, Icon }) => (
              <li key={to}>
                <NavLink to={to} className={navLinkClass}>
                  <Icon aria-hidden className="size-4" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main id="main" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-3 text-xs text-slate-600 sm:px-6">
          <p>
            ResQAI is a decision-support prototype. It does not dispatch emergency services, is not medical triage,
            and all resources shown are simulated.
          </p>
          <span className="flex flex-wrap items-center gap-2">
            <span>ResQAI v{__APP_VERSION__}</span>
            <HumanOversightNotice />
          </span>
        </div>
      </footer>
    </div>
  );
}
