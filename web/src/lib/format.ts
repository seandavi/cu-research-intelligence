import { track } from "./analytics";

export const fmtInt = (n: number | null | undefined): string =>
  n === null || n === undefined ? "—" : Math.round(n).toLocaleString();

export const fmtPct = (n: number | null | undefined, digits = 0): string =>
  n === null || n === undefined ? "—" : `${n.toFixed(digits)}%`;

export const fmtNum = (n: number | null | undefined, digits = 2): string =>
  n === null || n === undefined ? "—" : n.toFixed(digits);

// Compact USD: $1.2B / $340M / $51.3M / $250K.
export const fmtMoney = (n: number | null | undefined): string => {
  if (n === null || n === undefined) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${n}`;
};

export const shorten = (s: string, max = 26): string =>
  s.length <= max ? s : s.slice(0, max - 1) + "…";

// Program → stable color (matches the dashboard palette ordering).
const PALETTE = [
  "#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
  "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC",
];
export function programColors(programs: string[]): Record<string, string> {
  const sorted = [...new Set(programs)].sort();
  return Object.fromEntries(sorted.map((p, i) => [p, PALETTE[i % PALETTE.length]]));
}

// Trigger a client-side CSV download from an array of records.
export function downloadCsv(input: readonly object[], filename: string): void {
  const rows = input as readonly Record<string, unknown>[];
  if (!rows.length) return;
  track("export_csv", { dataset: filename, rows: rows.length });
  const cols = Object.keys(rows[0]);
  const esc = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Short labels for the strategic foci / retreat themes (full names are ~50 chars). */
export const FOCUS_SHORT: Record<string, string> = {
  "Structural, Molecular, and Cellular Biology": "Structural & Molecular",
  "Cancer Evolution from Initiation through Metastatic Spread": "Cancer Evolution",
  "Therapeutic Resistance": "Therapeutic Resistance",
  Immunotherapy: "Immunotherapy",
  "Cancer Interception and Survivorship": "Interception & Survivorship",
  "Clinical trial reports": "Clinical trials",
  "— of which phase I / first-in-human": "Phase I / FIH",
  "— of which randomized / phase III": "Randomized / phase III",
  "N-of-1, patient-centric & investigator-initiated trials": "N-of-1 / IIT",
};
export const shortFocus = (f: string) => FOCUS_SHORT[f] ?? f;
