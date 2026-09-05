import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { RetreatEntry, YearRange } from "../api/types";
import { Card, ErrorNote, KpiCard, Loading } from "../components/ui";
import { useMe, useMeta, useRetreatEntries, useRetreatThemes } from "../hooks/useApi";
import { downloadCsv, fmtInt } from "../lib/format";

const RETREAT_DATE = "2026-11-20";
const ABSTRACT_DEADLINE = "2026-09-14";
const PANEL_TOPICS = [
  "Barriers and opportunities in clinical trial design or accrual",
  "Translational pathways from discovery to implementation",
  "Emerging technologies or methodologies",
  "Broader issues in cancer research strategy and collaboration",
];
const DECISIONS = ["oral", "discussion", "poster", "declined"];
const daysUntil = (iso: string) => Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
const short = (p: string | null) => (p ?? "").replace(" & ", " & ").split(" ").map((w) => w[0]).join("");

export function Retreat({ range }: { range: YearRange }) {
  const meta = useMeta();
  const me = useMe();
  const themes = useRetreatThemes(range);
  const signedIn = me.data?.authenticated === true;
  const entries = useRetreatEntries(signedIn);
  const organizer = !!me.data?.roles?.some((r) => r === "leadership" || r === "admin");
  const [sel, setSel] = useState(0);

  const programs = meta.data?.current_programs ?? [];
  const rows = entries.data ?? [];
  const abstracts = rows.filter((r) => r.kind === "abstract");
  const questions = rows.filter((r) => r.kind === "question");
  const regs = rows.filter((r) => r.kind === "registration");
  const deadline = daysUntil(ABSTRACT_DEADLINE);

  if (themes.isLoading) return <Loading />;
  if (themes.error) return <ErrorNote error={themes.error} />;
  const t = themes.data ?? [];
  const cur = t[sel];

  return (
    <>
      <h1>Scientific Retreat 2026 — Advancing Our Strategic Vision</h1>
      <p className="lede">
        November 20, 2026. Keynote: <em>The Future of Cancer Clinical Trials</em> (Razelle Kurzrock,
        MD), followed by a panel with clinical-trial leaders. This page maps the retreat's themes onto
        what Cancer Center members actually publish, and tracks abstracts, panel questions, and
        registrations.
      </p>

      <div className="kpi-row">
        <KpiCard label="Abstracts submitted" value={signedIn ? fmtInt(abstracts.length) : "—"} />
        <KpiCard label="Panel questions" value={signedIn ? fmtInt(questions.length) : "—"} />
        <KpiCard label="Registrations" value={signedIn ? fmtInt(regs.length) : "—"} />
        <KpiCard
          label={deadline >= 0 ? "Days to abstract deadline" : "Days to retreat"}
          value={fmtInt(deadline >= 0 ? deadline : daysUntil(RETREAT_DATE))}
          hint={`Abstracts due ${ABSTRACT_DEADLINE}; retreat ${RETREAT_DATE}`}
        />
      </div>

      <Card
        title={`Retreat themes across member publications (${range.minYear}–${range.maxYear})`}
        action={<button onClick={() => downloadCsv(themeCsv(t, programs), "uccc_retreat_themes.csv")}>⬇ CSV</button>}
      >
        <p className="muted">
          A publication counts toward a theme when its title or abstract contains one of the theme's
          terms. Click a theme for its members and OpenAlex topics.
        </p>
        <table className="data compact">
          <thead>
            <tr>
              <th>Theme</th>
              <th className="num">Publications</th>
              <th className="num">Members</th>
              {programs.map((p) => (
                <th key={p} className="num" title={p}>
                  {short(p)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {t.map((th, i) => (
              <tr key={th.name} className={`clickable ${i === sel ? "sel" : ""}`} onClick={() => setSel(i)}>
                <td>
                  {th.name}
                  <div className="termlist">{th.terms.join(" · ")}</div>
                </td>
                <td className="num">{fmtInt(th.publications)}</td>
                <td className="num">{fmtInt(th.members)}</td>
                {programs.map((p) => (
                  <td key={p} className="num">
                    {fmtInt(th.by_program.find((b) => b.program === p)?.publications ?? 0)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {cur && (
        <div className="cols2">
          <Card title={`${cur.name}: most active members`}>
            <table className="data compact">
              <tbody>
                {cur.top_members.map((m) => (
                  <tr key={m.member_id}>
                    <td>
                      <Link to={`/members/${m.member_id}`}>{m.name}</Link>
                    </td>
                    <td className="muted">{m.program}</td>
                    <td className="num">{fmtInt(m.publications)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title={`${cur.name}: OpenAlex topics`}>
            <table className="data compact">
              <tbody>
                {cur.top_topics.map((x) => (
                  <tr key={x.topic}>
                    <td>{x.topic}</td>
                    <td className="num">{fmtInt(x.publications)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {!signedIn ? (
        <Card title="Submissions">
          <p className="muted">
            Abstracts, panel questions, and registrations are visible to signed-in CU Anschutz users.{" "}
            {me.error ? (
              <span>The submissions store is not enabled on this deployment.</span>
            ) : (
              <a href="/api/auth/login">Sign in</a>
            )}
          </p>
        </Card>
      ) : entries.error ? (
        <ErrorNote error={entries.error} />
      ) : (
        <>
          <Abstracts rows={abstracts} organizer={organizer} />
          <Questions rows={questions} />
          <Registrations rows={regs} programs={programs} />
        </>
      )}
    </>
  );
}

function themeCsv(t: { name: string; publications: number; members: number; by_program: { program: string; publications: number }[] }[], programs: string[]) {
  return t.map((th) => ({
    theme: th.name,
    publications: th.publications,
    members: th.members,
    ...Object.fromEntries(programs.map((p) => [p, th.by_program.find((b) => b.program === p)?.publications ?? 0])),
  }));
}

function Abstracts({ rows, organizer }: { rows: RetreatEntry[]; organizer: boolean }) {
  const qc = useQueryClient();
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: string | null }) => api.retreatDecide(id, { decision }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["retreat_entries"] }),
  });
  return (
    <Card
      title={`Abstracts (${rows.length})`}
      action={<button onClick={() => downloadCsv(rows.map(flat), "uccc_retreat_abstracts.csv")}>⬇ CSV</button>}
    >
      {rows.length === 0 && <p className="muted">No abstracts yet. Import the form export with <code>python -m cu_openalex.cancer_center.app.retreat abstract file.csv</code>.</p>}
      {rows.length > 0 && (
        <table className="data compact">
          <thead>
            <tr>
              <th>Title</th>
              <th>Submitter</th>
              <th>Program</th>
              <th>Format</th>
              <th>Themes</th>
              <th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td title={r.body ?? ""}>{r.title}</td>
                <td>{r.member_id ? <Link to={`/members/${r.member_id}`}>{r.name}</Link> : r.name}</td>
                <td className="muted">{r.program ?? "—"}</td>
                <td>{r.category ?? "—"}</td>
                <td>
                  {r.themes.map((th) => (
                    <span key={th} className="pchip">{th}</span>
                  ))}
                </td>
                <td>
                  {organizer ? (
                    <select
                      value={r.decision ?? ""}
                      onChange={(e) => decide.mutate({ id: r.id, decision: e.target.value || null })}
                    >
                      <option value="">—</option>
                      {DECISIONS.map((d) => (
                        <option key={d}>{d}</option>
                      ))}
                    </select>
                  ) : (
                    r.decision ?? "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function Questions({ rows }: { rows: RetreatEntry[] }) {
  const qc = useQueryClient();
  const [topic, setTopic] = useState(PANEL_TOPICS[0]);
  const [text, setText] = useState("");
  const submit = useMutation({
    mutationFn: () => api.retreatSubmit({ kind: "question", category: topic, body: text.trim() }),
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: ["retreat_entries"] });
    },
  });
  const byTopic = new Map<string, RetreatEntry[]>();
  for (const r of rows) byTopic.set(r.category ?? "Other", [...(byTopic.get(r.category ?? "Other") ?? []), r]);
  return (
    <Card
      title={`Panel questions — Future of Cancer Clinical Trials (${rows.length})`}
      action={<button onClick={() => downloadCsv(rows.map(flat), "uccc_retreat_panel_questions.csv")}>⬇ CSV</button>}
    >
      <form
        className="qform"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim()) submit.mutate();
        }}
      >
        <select value={topic} onChange={(e) => setTopic(e.target.value)}>
          {PANEL_TOPICS.map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <textarea placeholder="Your question for the panel…" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
        <div>
          <button type="submit" disabled={submit.isPending || !text.trim()}>Submit question</button>{" "}
          {submit.data?.duplicate && <span className="muted">Already submitted.</span>}
          {submit.error && <span className="error">{String(submit.error)}</span>}
        </div>
      </form>
      {[...byTopic.entries()].map(([cat, qs]) => (
        <div key={cat}>
          <h3 className="section">{cat} ({qs.length})</h3>
          <ul>
            {qs.map((r) => (
              <li key={r.id}>
                {r.body} <span className="muted">— {r.name}{r.program ? `, ${r.program}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </Card>
  );
}

function Registrations({ rows, programs }: { rows: RetreatEntry[]; programs: string[] }) {
  const count = (p: string | null) => rows.filter((r) => (r.program ?? null) === p).length;
  return (
    <Card
      title={`Registrations (${rows.length})`}
      action={<button onClick={() => downloadCsv(rows.map(flat), "uccc_retreat_registrations.csv")}>⬇ CSV</button>}
    >
      <table className="data compact">
        <tbody>
          {programs.map((p) => (
            <tr key={p}>
              <td>{p}</td>
              <td className="num">{fmtInt(count(p))}</td>
            </tr>
          ))}
          <tr>
            <td className="muted">Not matched to a member (lab members, guests)</td>
            <td className="num">{fmtInt(rows.filter((r) => !r.member_id).length)}</td>
          </tr>
        </tbody>
      </table>
    </Card>
  );
}

// Flatten an entry for CSV export (themes joined, extra form columns spread).
const flat = (r: RetreatEntry) => ({
  id: r.id,
  name: r.name,
  email: r.email,
  program: r.program,
  title: r.title,
  body: r.body,
  category: r.category,
  decision: r.decision,
  themes: r.themes.join("; "),
  created_at: r.created_at,
  ...r.extra,
});
