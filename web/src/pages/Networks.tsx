import { useMemo, useState } from "react";
import type { YearRange } from "../api/types";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { NetworkGraph } from "../components/NetworkGraph";
import { Card, Caveat, ErrorNote, Loading } from "../components/ui";
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

  // Prose summary of the graph — the canvas has no accessible content, so this
  // (plus the bridge table) is the text alternative. Rendered at page level so
  // it survives even if the force-graph canvas fails to initialize.
  const summary = useMemo(() => {
    if (!net.data) return "";
    const nPrograms = new Set(net.data.nodes.map((n) => n.program)).size;
    const top = bridges
      .slice(0, 5)
      .map((n) => `${n.name} (${n.program}, ${n.degree} co-authors)`);
    return (
      `Co-authorship network of ${net.data.nodes.length} cancer-center members across ` +
      `${nPrograms} programs, connected by ${net.data.edges.length} shared-publication ties. ` +
      (top.length ? `The most central bridge investigators are ${top.join("; ")}.` : "")
    );
  }, [net.data, bridges]);

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
                  <th>Member</th>
                  <th>Program</th>
                  <th className="num">Co-authors</th>
                  <th className="num">Betweenness</th>
                  <th className="num">Publications</th>
                </tr>
              </thead>
              <tbody>
                {bridges.map((n) => (
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
            <p className="net-summary">{summary}</p>
            <div className="legend">
              {[...new Set(net.data.nodes.map((n) => n.program))].sort().map((p) => (
                <span key={p} className="legend-item">
                  <span className="swatch" style={{ background: colors[p] }} />
                  {p}
                </span>
              ))}
            </div>
            <ErrorBoundary
              fallback={
                <div className="error">
                  The interactive graph couldn’t be displayed in this browser. The bridge
                  investigators are listed in the table above.
                </div>
              }
            >
              <NetworkGraph data={net.data} colors={colors} description={summary} />
            </ErrorBoundary>
          </Card>
        </>
      )}

      <Caveat />
    </>
  );
}
