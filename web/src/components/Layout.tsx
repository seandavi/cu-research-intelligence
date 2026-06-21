import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useMeta } from "../hooks/useApi";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/publications", label: "Publications" },
  { to: "/programs", label: "Program Collaboration" },
  { to: "/institutions", label: "Inter-institutional" },
  { to: "/funding", label: "NIH Funding", needsGrants: true },
  { to: "/networks", label: "Networks" },
  { to: "/members", label: "Members" },
  { to: "/ask", label: "Ask" },
];

export function Layout() {
  const meta = useMeta();
  const nav = NAV.filter((n) => !n.needsGrants || meta.data?.grants_available);
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
      </aside>
      <main className="content">
        <Suspense fallback={<div className="loading">Loading…</div>}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}
