import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { YearFilter } from "./components/ui";
import { useMeta } from "./hooks/useApi";
import { Overview } from "./pages/Overview";
import { Programs } from "./pages/Programs";
import { Networks } from "./pages/Networks";
import { Members } from "./pages/Members";
import { MemberProfile } from "./pages/MemberProfile";
import { Ask } from "./pages/Ask";
import type { YearRange } from "./api/types";

export function App() {
  const meta = useMeta();
  const [range, setRange] = useState<YearRange | null>(null);

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
        <Route path="programs" element={<WithFilter range={range} setRange={setRange}>{(r) => <Programs range={r} />}</WithFilter>} />
        <Route path="networks" element={<WithFilter range={range} setRange={setRange}>{(r) => <Networks range={r} />}</WithFilter>} />
        <Route path="members" element={<WithFilter range={range} setRange={setRange}>{(r) => <Members range={r} />}</WithFilter>} />
        <Route path="members/:id" element={<WithFilter range={range} setRange={setRange}>{(r) => <MemberProfile range={r} />}</WithFilter>} />
        <Route path="ask" element={<Ask />} />
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
        <YearFilter value={range} bounds={{ min: 2000, max: 2025 }} onChange={setRange} />
      </div>
      {children(range)}
    </>
  );
}
