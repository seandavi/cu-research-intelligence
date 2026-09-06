import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useMeta } from "../hooks/useApi";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/publications", label: "Publications" },
  { to: "/programs", label: "Program Collaboration" },
  { to: "/foci", label: "Strategic Foci" },
  { to: "/institutions", label: "Inter-institutional" },
  { to: "/funding", label: "NIH Funding", needsGrants: true },
  { to: "/networks", label: "Networks" },
  { to: "/members", label: "Members" },
  { to: "/ask", label: "Ask" },
  { to: "/about", label: "About" },
];

// Footer labels for the freshness stamps in /api/meta; unknown keys are skipped.
const FRESHNESS: [string, string][] = [
  ["openalex_works_watermark", "OpenAlex snapshot"],
  ["icite_version", "iCite"],
  ["reporter_version", "NIH RePORTER"],
  ["roster_snapshot", "Member roster"],
  ["built_at", "Built"],
];

export function Layout() {
  const meta = useMeta();
  const nav = NAV.filter((n) => !n.needsGrants || meta.data?.grants_available);
  const fresh = meta.data?.data_freshness ?? {};
  const stamps = FRESHNESS.filter(([k]) => fresh[k]);
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-title">UCCC</div>
          <div className="brand-sub">Research Intelligence</div>
        </div>
        <nav>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => (isActive ? "active" : "")}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        {stamps.length > 0 && (
          <div className="sidebar-foot">
            <div>Data as of</div>
            {stamps.map(([k, label]) => (
              <div key={k}>
                {label}: <span>{fresh[k].slice(0, 10)}</span>
              </div>
            ))}
          </div>
        )}
      </aside>
      <main className="content">
        <Suspense fallback={<div className="loading">Loading…</div>}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
