import { useMemo, useState, type ReactNode } from "react";

export function KpiCard({
  label,
  value,
  hint,
  delta,
}: {
  label: string;
  value: string;
  hint?: string;
  delta?: { value: string; positive: boolean } | null;
}) {
  return (
    <div className="kpi" title={hint}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {delta && (
        <div className={`kpi-delta ${delta.positive ? "up" : "down"}`}>
          {delta.positive ? "▲" : "▼"} {delta.value}
        </div>
      )}
    </div>
  );
}

export function Card({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className="card">
      {(title || action) && (
        <div className="card-head">
          {title && <h2>{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function YearFilter({
  value,
  bounds,
  onChange,
}: {
  value: { minYear: number; maxYear: number };
  bounds: { min: number; max: number };
  onChange: (v: { minYear: number; maxYear: number }) => void;
}) {
  return (
    <div className="yearfilter">
      <label>Years</label>
      <input
        type="number"
        min={bounds.min}
        max={value.maxYear}
        value={value.minYear}
        onChange={(e) => onChange({ ...value, minYear: Number(e.target.value) })}
      />
      <span>–</span>
      <input
        type="number"
        min={value.minYear}
        max={bounds.max}
        value={value.maxYear}
        onChange={(e) => onChange({ ...value, maxYear: Number(e.target.value) })}
      />
    </div>
  );
}

export function Caveat({ provisional }: { provisional?: boolean }) {
  return (
    <p className="caveat">
      <strong>About this data.</strong> Counts are peer-reviewed articles &amp; reviews —
      preprints, datasets, and conference abstracts excluded. Impact uses FWCI and NIH iCite{" "}
      <strong>RCR</strong> (1.0 = median NIH-funded paper). Members are matched to OpenAlex by
      ORCID and name (~675/1,115 resolve), so collaboration figures are lower bounds; only ORCID
      matches are identity-verified. Within-year ratios are more reliable than absolute counts.
      {provisional && " Recent years are provisional (OpenAlex indexing lag)."}
    </p>
  );
}

export function Loading() {
  return <div className="loading">Loading…</div>;
}

export function ErrorNote({ error }: { error: unknown }) {
  return <div className="error">Failed to load: {String((error as Error)?.message ?? error)}</div>;
}

// --- Sortable table headers ---------------------------------------------------
// useSort(rows) sorts an in-memory array by a row key; <Th> renders a clickable header.
// Server-paginated tables pass their own {sort, toggle} so header clicks drive the API sort.

export type SortState = { key: string; dir: 1 | -1 } | null;
export type SortCtl = { sort: SortState; toggle: (key: string, first: 1 | -1) => void };

// Nulls sort last in either direction; arrays sort by length (e.g. a member's foci).
function cmp(a: unknown, b: unknown): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (Array.isArray(a) && Array.isArray(b)) return a.length - b.length;
  return String(a).localeCompare(String(b));
}

export function useSort<T>(rows: readonly T[]): SortCtl & { rows: T[] } {
  const [sort, setSort] = useState<SortState>(null);
  const sorted = useMemo(() => {
    if (!sort) return [...rows];
    const { key, dir } = sort;
    return [...rows].sort((a, b) => {
      const x = (a as Record<string, unknown>)[key];
      const y = (b as Record<string, unknown>)[key];
      if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
      return cmp(x, y) * dir;
    });
  }, [rows, sort]);
  // Click cycle: first direction → opposite → original order.
  const toggle = (key: string, first: 1 | -1) =>
    setSort((s) => (s?.key !== key ? { key, dir: first } : s.dir === first ? { key, dir: -first as 1 | -1 } : null));
  return { rows: sorted, sort, toggle };
}

export function Th({
  k,
  ctl,
  num,
  title,
  children,
}: {
  k: string;
  ctl: SortCtl;
  num?: boolean;
  title?: string;
  children: ReactNode;
}) {
  const dir = ctl.sort?.key === k ? ctl.sort.dir : 0;
  return (
    <th
      className={num ? "num" : undefined}
      title={title}
      aria-sort={dir === 1 ? "ascending" : dir === -1 ? "descending" : "none"}
    >
      <button className="sort" onClick={() => ctl.toggle(k, num ? -1 : 1)}>
        {children}
        <span className="sort-arrow">{dir === 1 ? "▲" : dir === -1 ? "▼" : "⇅"}</span>
      </button>
    </th>
  );
}
