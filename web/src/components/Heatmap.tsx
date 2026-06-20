import type { MatrixCell } from "../api/types";
import { shorten } from "../lib/format";

// Program × program co-authorship heatmap. Diagonal = intra-programmatic
// (≥2 members of one program); off-diagonal = inter-programmatic ties.
export function Heatmap({ cells, programs }: { cells: MatrixCell[]; programs: string[] }) {
  const lookup = new Map<string, number>();
  let max = 1;
  for (const c of cells) {
    lookup.set(`${c.prog_a}|${c.prog_b}`, c.publications);
    lookup.set(`${c.prog_b}|${c.prog_a}`, c.publications);
    max = Math.max(max, c.publications);
  }
  const val = (a: string, b: string) => lookup.get(`${a}|${b}`) ?? 0;
  const color = (v: number) => {
    const t = v / max; // 0..1 → light to deep blue
    const l = 96 - t * 58;
    return `hsl(211 56% ${l}%)`;
  };

  return (
    <div className="heatmap" style={{ gridTemplateColumns: `minmax(120px,1fr) repeat(${programs.length}, 1fr)` }}>
      <div className="hm-corner" />
      {programs.map((p) => (
        <div key={`h-${p}`} className="hm-colhead" title={p}>
          {shorten(p, 18)}
        </div>
      ))}
      {programs.map((row) => (
        <Row key={row} row={row} programs={programs} val={val} color={color} max={max} />
      ))}
    </div>
  );
}

function Row({
  row,
  programs,
  val,
  color,
  max,
}: {
  row: string;
  programs: string[];
  val: (a: string, b: string) => number;
  color: (v: number) => string;
  max: number;
}) {
  return (
    <>
      <div className="hm-rowhead" title={row}>
        {shorten(row, 22)}
      </div>
      {programs.map((col) => {
        const v = val(row, col);
        return (
          <div
            key={`${row}-${col}`}
            className="hm-cell"
            style={{ background: color(v), color: v > max * 0.55 ? "#fff" : "#222" }}
            title={`${row} × ${col}: ${v.toLocaleString()} publications`}
          >
            {v || ""}
          </div>
        );
      })}
    </>
  );
}
