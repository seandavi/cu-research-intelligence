import { useEffect, useMemo, useRef, useState } from "react";
import type { FC } from "react";
import { UpSetJS as RawUpSetJS, extractCombinations } from "@upsetjs/react";
import type { ProgramCombination } from "../api/types";
import { shorten } from "../lib/format";

// @upsetjs/react bundles an older @types/react, which trips the JSX-component
// type check under React 18. The runtime is fine — cast to a permissive FC.
const UpSetJS = RawUpSetJS as unknown as FC<Record<string, unknown>>;

interface Elem {
  name: string;
  sets: string[];
}

// UpSet plot of program co-authorship: each combination of programs and the
// number of publications spanning exactly that set. Built from aggregated
// counts expanded into synthetic elements (one per publication).
export function UpsetPlot({
  combos,
  height = 430,
}: {
  combos: ProgramCombination[];
  height?: number;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(760);
  const [hover, setHover] = useState<unknown>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const { sets, combinations } = useMemo(() => {
    const elems: Elem[] = [];
    let id = 0;
    for (const c of combos) {
      const setNames = c.programs.map((p) => shorten(p, 22));
      for (let i = 0; i < c.count; i++) elems.push({ name: `w${id++}`, sets: setNames });
    }
    return extractCombinations(elems);
  }, [combos]);

  if (!combos.length) return <p className="muted">No program combinations in this window.</p>;

  return (
    <div ref={wrapRef}>
      <UpSetJS
        sets={sets}
        combinations={combinations}
        width={width}
        height={height}
        selection={hover}
        onHover={setHover}
        theme="light"
        color="#4C78A8"
        selectionColor="#F58518"
        exportButtons={false}
      />
    </div>
  );
}
