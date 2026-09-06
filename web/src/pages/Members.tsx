import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { YearRange } from "../api/types";
import { Card, Caveat, ErrorNote, Loading, Th, useSort } from "../components/ui";
import { useMembers, useRetreatThemes } from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtNum, shortFocus } from "../lib/format";

export function Members({ range }: { range: YearRange }) {
  const [search, setSearch] = useState("");
  const [program, setProgram] = useState("All");
  const [focus, setFocus] = useState("");
  const [multiFoci, setMultiFoci] = useState(false);
  const members = useMembers(range, focus || undefined, multiFoci ? 2 : undefined);
  const foci = useRetreatThemes(range);

  const rows = members.data ?? [];
  const programs = useMemo(
    () => ["All", ...[...new Set(rows.map((r) => r.program).filter(Boolean))].sort()],
    [rows],
  );
  const filtered = rows.filter(
    (r) =>
      (program === "All" || r.program === program) &&
      (!search || r.name.toLowerCase().includes(search.toLowerCase())),
  );

  const sorted = useSort(filtered);

  if (members.isLoading) return <Loading />;
  if (members.error) return <ErrorNote error={members.error} />;

  return (
    <>
      <h1>Member Directory</h1>
      <p className="lede">
        Per-member productivity and match quality (resolved members). <em>Match</em> = how reliably
        a member was linked to OpenAlex (high = ORCID-verified).
      </p>

      <div className="filters">
        <input placeholder="Search name…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select value={program} onChange={(e) => setProgram(e.target.value)}>
          {programs.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <select value={focus} onChange={(e) => setFocus(e.target.value)}>
          <option value="">Any focus</option>
          {(foci.data?.themes ?? []).map((f) => (
            <option key={f.name} value={f.name}>
              {f.name}
            </option>
          ))}
        </select>
        <label className="chk">
          <input type="checkbox" checked={multiFoci} onChange={(e) => setMultiFoci(e.target.checked)} />
          Works in ≥2 foci
        </label>
        <span className="muted">{filtered.length} members</span>
        <button onClick={() => downloadCsv(filtered, "uccc_member_directory.csv")}>⬇ CSV</button>
      </div>

      <Card>
        <table className="data">
          <thead>
            <tr>
              <Th k="name" ctl={sorted}>Name</Th>
              <Th k="program" ctl={sorted}>Program</Th>
              <Th k="rank" ctl={sorted}>Rank</Th>
              <Th k="status" ctl={sorted}>Status</Th>
              <Th k="match_confidence" ctl={sorted}>Match</Th>
              <Th k="foci" ctl={sorted} title="Sorts by number of foci">Foci</Th>
              <Th k="publications" ctl={sorted} num>Publications</Th>
              <Th k="citations" ctl={sorted} num>Citations</Th>
              <Th k="mean_fwci" ctl={sorted} num>Mean FWCI</Th>
            </tr>
          </thead>
          <tbody>
            {sorted.rows.map((r) => (
              <tr key={r.member_id}>
                <td>
                  <Link to={`/members/${r.member_id}`}>{r.name}</Link>
                </td>
                <td>{r.program}</td>
                <td>{r.rank}</td>
                <td>{r.status}</td>
                <td>
                  <span className={`badge ${r.match_confidence ?? ""}`}>{r.match_confidence ?? "—"}</span>
                </td>
                <td>
                  {r.foci.map((f) => (
                    <span key={f} className="pchip" title={f}>
                      {shortFocus(f)}
                    </span>
                  ))}
                </td>
                <td className="num">{fmtInt(r.publications)}</td>
                <td className="num">{fmtInt(r.citations)}</td>
                <td className="num">{fmtNum(r.mean_fwci)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Caveat />
    </>
  );
}
