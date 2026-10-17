import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { NetworkData } from "../api/types";

// Co-authorship force graph. Nodes = members (size ∝ publications, color =
// program), links = shared publications. Hover for details; drag to reposition.
// The graph is drawn to a <canvas> with no accessible content, so it's labeled
// as an image via `description` (the page also renders that text and a ranked
// table so the information survives without the canvas).
export function NetworkGraph({
  data,
  colors,
  description,
  height = 600,
}: {
  data: NetworkData;
  colors: Record<string, string>;
  description?: string;
  height?: number;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  // Clone into the {nodes, links} shape the lib mutates (don't mutate query data).
  const graphData = useMemo(
    () => ({
      nodes: data.nodes.map((n) => ({ ...n })),
      links: data.edges.map((e) => ({ source: e.source, target: e.target, weight: e.weight })),
    }),
    [data],
  );
  const maxWeight = useMemo(
    () => Math.max(1, ...data.edges.map((e) => e.weight)),
    [data],
  );

  return (
    <div
      ref={wrapRef}
      className="network-wrap"
      style={{ height }}
      role="img"
      aria-label={description ?? "Co-authorship network diagram"}
    >
        <ForceGraph2D
          graphData={graphData}
          width={width}
          height={height}
          backgroundColor="#ffffff"
          nodeId="id"
          nodeVal={(n: any) => Math.max(1, n.publications)}
          nodeRelSize={2}
          nodeColor={(n: any) => colors[n.program] ?? "#888"}
          nodeLabel={(n: any) =>
            `${n.name} · ${n.program} · ${n.publications} pubs · ${n.degree} co-authors`
          }
          linkColor={() => "rgba(120,130,150,0.25)"}
          linkWidth={(l: any) => 0.4 + (l.weight / maxWeight) * 3}
          cooldownTicks={120}
          warmupTicks={40}
        />
    </div>
  );
}
