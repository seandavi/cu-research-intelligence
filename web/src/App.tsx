import { lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./components/Layout";
import { YearFilter } from "./components/ui";
import { useMeta } from "./hooks/useApi";
import { trackPageView } from "./lib/analytics";
import type { YearRange } from "./api/types";

// Lazy-load each route so the heavy libs (recharts, force-graph, UpSet.js) ship
// in per-route chunks loaded on demand, keeping the initial bundle light.
const Overview = lazy(() => import("./pages/Overview").then((m) => ({ default: m.Overview })));
const Publications = lazy(() =>
  import("./pages/Publications").then((m) => ({ default: m.Publications })),
);
const Programs = lazy(() => import("./pages/Programs").then((m) => ({ default: m.Programs })));
const Foci = lazy(() => import("./pages/Foci").then((m) => ({ default: m.Foci })));
const Institutions = lazy(() =>
  import("./pages/Institutions").then((m) => ({ default: m.Institutions })),
);
const Funding = lazy(() => import("./pages/Funding").then((m) => ({ default: m.Funding })));
const Networks = lazy(() => import("./pages/Networks").then((m) => ({ default: m.Networks })));
const Members = lazy(() => import("./pages/Members").then((m) => ({ default: m.Members })));
const MemberProfile = lazy(() =>
  import("./pages/MemberProfile").then((m) => ({ default: m.MemberProfile })),
);
const Ask = lazy(() => import("./pages/Ask").then((m) => ({ default: m.Ask })));

export function App() {
  const meta = useMeta();
  const location = useLocation();
  const [range, setRange] = useState<YearRange | null>(null);

  // SPA page-view tracking on every route change.
  useEffect(() => {
    trackPageView(location.pathname + location.search);
  }, [location.pathname, location.search]);

  // Initialize the year range from the API's default 7-year window once.
  useEffect(() => {
    if (meta.data && !range) {
      setRange({ minYear: meta.data.default_min_year, maxYear: meta.data.default_max_year });
    }
  }, [meta.data, range]);

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<WithFilter range={range} setRange={setRange}>{(r) => <Overview range={r} />}</WithFilter>} />
        <Route path="publications" element={<WithFilter range={range} setRange={setRange}>{(r) => <Publications range={r} />}</WithFilter>} />
        <Route path="programs" element={<WithFilter range={range} setRange={setRange}>{(r) => <Programs range={r} />}</WithFilter>} />
        <Route path="foci" element={<WithFilter range={range} setRange={setRange}>{(r) => <Foci range={r} />}</WithFilter>} />
        <Route path="institutions" element={<WithFilter range={range} setRange={setRange}>{(r) => <Institutions range={r} />}</WithFilter>} />
        <Route path="funding" element={<WithFilter range={range} setRange={setRange}>{(r) => <Funding range={r} />}</WithFilter>} />
        <Route path="networks" element={<WithFilter range={range} setRange={setRange}>{(r) => <Networks range={r} />}</WithFilter>} />
        <Route path="members" element={<WithFilter range={range} setRange={setRange}>{(r) => <Members range={r} />}</WithFilter>} />
        <Route path="members/:id" element={<WithFilter range={range} setRange={setRange}>{(r) => <MemberProfile range={r} />}</WithFilter>} />
        <Route path="ask" element={<Ask />} />
        <Route path="retreat" element={<Navigate to="/foci" replace />} />
      </Route>
    </Routes>
  );
}

// Renders the shared year filter (top-right) and the page once a range exists.
function WithFilter({
  range,
  setRange,
  children,
}: {
  range: YearRange | null;
  setRange: (r: YearRange) => void;
  children: (r: YearRange) => React.ReactNode;
}) {
  if (!range) return <div className="loading">Loading…</div>;
  return (
    <>
      <div className="topbar">
        <YearFilter value={range} bounds={{ min: 2000, max: new Date().getFullYear() }} onChange={setRange} />
      </div>
      {children(range)}
    </>
  );
}
