import type { ReactNode } from "react";

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
