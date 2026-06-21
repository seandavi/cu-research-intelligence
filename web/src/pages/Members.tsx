import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { YearRange } from "../api/types";
import { Card, Caveat, ErrorNote, Loading } from "../components/ui";
import { useMembers } from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtNum } from "../lib/format";

export function Members({ range }: { range: YearRange }) {
  const members = useMembers(range);
  const [search, setSearch] = useState("");
  const [program, setProgram] = useState("All");

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
        <span className="muted">{filtered.length} members</span>
        <button onClick={() => downloadCsv(filtered, "uccc_member_directory.csv")}>⬇ CSV</button>
      </div>

      <Card>
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th>Program</th>
              <th>Rank</th>
              <th>Status</th>
              <th>Match</th>
              <th className="num">Publications</th>
              <th className="num">Citations</th>
              <th className="num">Mean FWCI</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
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
