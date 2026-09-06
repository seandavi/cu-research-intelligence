import { useMemo, useState } from "react";
import type { YearRange } from "../api/types";
import { NetworkGraph } from "../components/NetworkGraph";
import { Card, Caveat, ErrorNote, Loading, Th, useSort } from "../components/ui";
import { useMeta, useNetwork } from "../hooks/useApi";
import { fmtInt, fmtNum, programColors } from "../lib/format";

export function Networks({ range }: { range: YearRange }) {
  const [minShared, setMinShared] = useState(3);
  const meta = useMeta();
  const net = useNetwork(range, minShared);

  const programs = meta.data?.current_programs ?? [];
  // Color every program that appears (current + deprecated), stable by name.
  const colors = useMemo(() => {
    const all = new Set<string>(programs);
    net.data?.nodes.forEach((n) => all.add(n.program));
    return programColors([...all]);
  }, [net.data, programs]);

  const bridges = useMemo(
    () => [...(net.data?.nodes ?? [])].sort((a, b) => b.betweenness - a.betweenness).slice(0, 15),
    [net.data],
  );
  const sorted = useSort(bridges);

  return (
    <>
      <h1>Co-authorship Networks</h1>
      <p className="lede">
        Members are nodes; edges are shared publications. Node size scales with publication count,
        color encodes program. Bridge investigators (high betweenness) connect otherwise-separate
        communities — often the engine of inter-programmatic science.
      </p>

      <div className="filters">
        <label>
          Min. shared publications per tie:&nbsp;<strong>{minShared}</strong>
        </label>
        <input
          type="range"
          min={1}
          max={10}
          value={minShared}
          onChange={(e) => setMinShared(Number(e.target.value))}
        />
      </div>

      {net.isLoading && <Loading />}
      {net.error && <ErrorNote error={net.error} />}
      {net.data && (
        <>
          <div className="net-stats">
            <span>{fmtInt(net.data.nodes.length)} members</span>
            <span>{fmtInt(net.data.edges.length)} co-authorship ties</span>
          </div>

          <Card title="Bridge investigators (by betweenness centrality)">
            <table className="data compact">
              <thead>
                <tr>
                  <Th k="name" ctl={sorted}>Member</Th>
                  <Th k="program" ctl={sorted}>Program</Th>
                  <Th k="degree" ctl={sorted} num>Co-authors</Th>
                  <Th k="betweenness" ctl={sorted} num>Betweenness</Th>
                  <Th k="publications" ctl={sorted} num>Publications</Th>
                </tr>
              </thead>
              <tbody>
                {sorted.rows.map((n) => (
                  <tr key={n.id}>
                    <td>{n.name}</td>
                    <td>{n.program}</td>
                    <td className="num">{n.degree}</td>
                    <td className="num">{fmtNum(n.betweenness, 3)}</td>
                    <td className="num">{fmtInt(n.publications)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>

          <Card title="Co-authorship graph">
            <div className="legend">
              {[...new Set(net.data.nodes.map((n) => n.program))].sort().map((p) => (
                <span key={p} className="legend-item">
                  <span className="swatch" style={{ background: colors[p] }} />
                  {p}
                </span>
              ))}
            </div>
            <NetworkGraph data={net.data} colors={colors} />
          </Card>
        </>
      )}

      <Caveat />
    </>
  );
}
