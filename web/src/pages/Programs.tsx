import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { YearRange } from "../api/types";
import { Heatmap } from "../components/Heatmap";
import { UpsetPlot } from "../components/UpsetPlot";
import { Card, Caveat, ErrorNote, Loading, Th, useSort } from "../components/ui";
import {
  useCollaborationMatrix,
  useProgramCombinations,
  useProgramSummary,
} from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtNum, shorten } from "../lib/format";

export function Programs({ range }: { range: YearRange }) {
  const [currentOnly, setCurrentOnly] = useState(true);
  const summary = useProgramSummary(range, currentOnly);
  const matrix = useCollaborationMatrix(range, currentOnly);
  const combos = useProgramCombinations(range, currentOnly);
  const sorted = useSort(summary.data ?? []);

  if (summary.isLoading || matrix.isLoading) return <Loading />;
  if (summary.error) return <ErrorNote error={summary.error} />;

  const rows = summary.data ?? [];
  const programs = rows.map((r) => r.program);
  const bars = rows.map((r) => ({ ...r, short: shorten(r.program, 22) }));

  return (
    <>
      <h1>Program Collaboration</h1>
      <p className="lede">
        Intra- and inter-programmatic co-authorship — the metric an NIH CCSG External Advisory
        Board scrutinizes. Strict-Members convention; a paper can be both.
      </p>
      <label className="toggle">
        <input type="checkbox" checked={!currentOnly} onChange={(e) => setCurrentOnly(!e.target.checked)} />
        Include deprecated programs
      </label>

      <Card title="Program × program co-authorship">
        <p className="hint">
          Cell = publications co-authored by both programs. Diagonal = intra-programmatic (≥2
          members of that program), not total output.
        </p>
        {matrix.data && <Heatmap cells={matrix.data} programs={programs} />}
      </Card>

      <Card title="Program combinations (UpSet)">
        <p className="hint">
          Publications by the exact set of programs that co-author them. Single-program bars are
          intra-only; multi-program bars are the inter-programmatic intersections the pairwise
          heatmap can't show (e.g. three programs on one paper).
        </p>
        {combos.data && <UpsetPlot combos={combos.data} />}
      </Card>

      <div className="grid-2">
        <Card title="Inter-programmatic % by program">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={bars} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis type="number" unit="%" />
              <YAxis type="category" dataKey="short" width={150} />
              <Tooltip />
              <Bar dataKey="pct_inter_program" fill="#F58518" name="Inter %" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Intra-programmatic % by program">
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={bars} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis type="number" unit="%" />
              <YAxis type="category" dataKey="short" width={150} />
              <Tooltip />
              <Bar dataKey="pct_intra_program" fill="#4C78A8" name="Intra %" />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card
        title="CCSG program publication summary"
        action={
          <button onClick={() => downloadCsv(rows, `uccc_program_summary_${range.minYear}-${range.maxYear}.csv`)}>
            ⬇ CSV
          </button>
        }
      >
        <table className="data">
          <thead>
            <tr>
              <Th k="program" ctl={sorted}>Program</Th>
              <Th k="publications" ctl={sorted} num>Publications</Th>
              <Th k="citations" ctl={sorted} num>Citations</Th>
              <Th k="mean_fwci" ctl={sorted} num>Mean FWCI</Th>
              <Th k="median_rcr" ctl={sorted} num>Median RCR</Th>
              <Th k="pct_inter_program" ctl={sorted} num>Inter %</Th>
              <Th k="pct_intra_program" ctl={sorted} num>Intra %</Th>
            </tr>
          </thead>
          <tbody>
            {sorted.rows.map((r) => (
              <tr key={r.program}>
                <td>{r.program}</td>
                <td className="num">{fmtInt(r.publications)}</td>
                <td className="num">{fmtInt(r.citations)}</td>
                <td className="num">{fmtNum(r.mean_fwci)}</td>
                <td className="num">{fmtNum(r.median_rcr)}</td>
                <td className="num">{fmtNum(r.pct_inter_program, 1)}</td>
                <td className="num">{fmtNum(r.pct_intra_program, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Caveat />
    </>
  );
}
