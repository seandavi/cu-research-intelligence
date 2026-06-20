import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/programs", label: "Program Collaboration" },
  { to: "/institutions", label: "Inter-institutional" },
  { to: "/networks", label: "Networks" },
  { to: "/members", label: "Members" },
  { to: "/ask", label: "Ask" },
];

export function Layout() {
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-title">UCCC</div>
          <div className="brand-sub">Research Intelligence</div>
        </div>
        <nav>
          {NAV.map((n) => (
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
