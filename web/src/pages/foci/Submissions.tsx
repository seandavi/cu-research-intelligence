import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { RetreatEntry } from "../../api/types";
import { Card } from "../../components/ui";
import { downloadCsv, fmtInt, initials } from "../../lib/format";

// Retreat 2026 submissions (abstracts, panel questions, registrations) over the
// app-tier store; rendered at the bottom of the Strategic Foci page.
const PANEL_TOPICS = [
  "Barriers and opportunities in clinical trial design or accrual",
  "Translational pathways from discovery to implementation",
  "Emerging technologies or methodologies",
  "Broader issues in cancer research strategy and collaboration",
];
const DECISIONS = ["oral", "discussion", "poster", "declined"];
const QUESTION_DECISIONS = ["star", "ask live", "merged", "declined"];
// Run-of-show order for panel questions.
const Q_WEIGHT: Record<string, number> = { "ask live": 0, star: 1, "": 2, merged: 3, declined: 4 };
const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

export function Mine({ rows }: { rows: RetreatEntry[] }) {
  return (
    <Card title="Your retreat submissions">
      {rows.length === 0 ? (
        <p className="muted">Nothing on file for your email yet. Abstract and registration form exports are loaded by the committee, so a submission can take a few days to appear.</p>
      ) : (
        <table className="data compact">
          <thead>
            <tr><th>Type</th><th>Title / text</th><th>Format / topic</th><th>Status</th><th>Received</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>{r.kind}</td>
                <td>{r.title ?? r.body}</td>
                <td>{r.category ?? "—"}</td>
                <td><span className="status">{r.decision ?? "received"}</span></td>
                <td className="muted">{fmtDate(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

export function Abstracts({ rows }: { rows: RetreatEntry[] }) {
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
      {rows.length === 0 && (
        <p className="muted">
          No abstracts loaded yet. Import the form export with{" "}
          <code>python -m cu_openalex.cancer_center.app.retreat abstract export.csv --map "Response ID=source_id" …</code>
        </p>
      )}
      {rows.length > 0 && (
        <table className="data compact">
          <thead>
            <tr>
              <th>Title</th><th>Submitter</th><th>Role</th><th>Program</th><th>Format</th><th>Themes</th><th>Decision</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td title={r.body ?? ""}>{r.title}</td>
                <td>{r.member_id ? <Link to={`/members/${r.member_id}`}>{r.name}</Link> : r.name}</td>
                <td className="muted">{r.role ?? (r.member_id ? "member" : "—")}</td>
                <td className="muted">{initials(r.program) || "—"}</td>
                <td>{r.category ?? "—"}</td>
                <td>{r.themes.map((th) => <span key={th} className="pchip">{th}</span>)}</td>
                <td>
                  <select value={r.decision ?? ""} onChange={(e) => decide.mutate({ id: r.id, decision: e.target.value || null })}>
                    <option value="">—</option>
                    {DECISIONS.map((d) => <option key={d}>{d}</option>)}
                  </select>
                  {r.decided_at && (
                    <div className="termlist">{r.decided_by ?? "?"} · {fmtDate(r.decided_at)}</div>
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

export function Questions({ rows, organizer }: { rows: RetreatEntry[]; organizer: boolean }) {
  const qc = useQueryClient();
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: number; decision: string | null }) => api.retreatDecide(id, { decision }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["retreat_entries"] }),
  });
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
  const ordered = [...rows].sort((a, b) => (Q_WEIGHT[a.decision ?? ""] ?? 2) - (Q_WEIGHT[b.decision ?? ""] ?? 2));
  for (const r of ordered) byTopic.set(r.category ?? "Other", [...(byTopic.get(r.category ?? "Other") ?? []), r]);
  return (
    <Card
      title={`Panel questions — Future of Cancer Clinical Trials (${rows.length})`}
      action={organizer ? <button onClick={() => downloadCsv(rows.map(flat), "uccc_retreat_panel_questions.csv")}>⬇ CSV</button> : null}
    >
      <form className="qform" onSubmit={(e) => { e.preventDefault(); if (text.trim()) submit.mutate(); }}>
        <select value={topic} onChange={(e) => setTopic(e.target.value)}>
          {PANEL_TOPICS.map((p) => <option key={p}>{p}</option>)}
        </select>
        <textarea placeholder="Your question for the panel…" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} />
        <div>
          <button type="submit" disabled={submit.isPending || !text.trim()}>Submit question</button>{" "}
          {submit.data && !submit.data.inserted && <span className="muted">Already submitted.</span>}
          {submit.error && <span className="error">{String(submit.error)}</span>}
          <span className="muted"> Questions are shown to everyone without names; the committee sees who asked{organizer ? " and can star, mark to ask live, merge, or decline" : ""}.</span>
        </div>
      </form>
      {[...byTopic.entries()].map(([cat, qs]) => (
        <div key={cat}>
          <h3 className="section">{cat} ({qs.length})</h3>
          <ul>
            {qs.map((r) => (
              <li key={r.id} className={r.decision === "star" || r.decision === "ask live" ? "starred" : r.decision === "merged" || r.decision === "declined" ? "muted" : ""}>
                {r.body}
                {(organizer || r.mine) && (
                  <span className="muted"> — {r.mine && !organizer ? "you" : r.name}{r.program ? `, ${initials(r.program)}` : ""}</span>
                )}
                {organizer && (
                  <>
                    {" "}
                    <select value={r.decision ?? ""} onChange={(e) => decide.mutate({ id: r.id, decision: e.target.value || null })}>
                      <option value="">—</option>
                      {QUESTION_DECISIONS.map((d) => <option key={d}>{d}</option>)}
                    </select>
                  </>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </Card>
  );
}

export function Registrations({ rows, programs }: { rows: RetreatEntry[]; programs: string[] }) {
  const count = (f: (r: RetreatEntry) => boolean) => rows.filter(f).length;
  const roles = [...new Set(rows.map((r) => r.role ?? (r.member_id ? "member" : "unmatched")))].sort();
  return (
    <Card
      title={`Registrations (${rows.length})`}
      action={<button onClick={() => downloadCsv(rows.map(flat), "uccc_retreat_registrations.csv")}>⬇ CSV</button>}
    >
      <div className="cols2">
        <table className="data compact">
          <thead><tr><th>By program (members)</th><th className="num">n</th></tr></thead>
          <tbody>
            {programs.map((p) => (
              <tr key={p}><td>{p}</td><td className="num">{fmtInt(count((r) => r.program === p))}</td></tr>
            ))}
            <tr><td className="muted">Not matched to a member (lab members, guests)</td><td className="num">{fmtInt(count((r) => !r.member_id))}</td></tr>
          </tbody>
        </table>
        <table className="data compact">
          <thead><tr><th>By role (from the form)</th><th className="num">n</th></tr></thead>
          <tbody>
            {roles.map((role) => (
              <tr key={role}><td>{role}</td><td className="num">{fmtInt(count((r) => (r.role ?? (r.member_id ? "member" : "unmatched")) === role))}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// Flatten an entry for CSV export (themes joined, extra form columns spread).
const flat = (r: RetreatEntry) => ({
  id: r.id,
  source_id: r.source_id,
  name: r.name,
  email: r.email,
  role: r.role,
  program: r.program,
  title: r.title,
  body: r.body,
  category: r.category,
  decision: r.decision,
  decided_by: r.decided_by,
  decided_at: r.decided_at,
  themes: r.themes.join("; "),
  created_at: r.created_at,
  import_file: r.import_file,
  imported_at: r.imported_at,
  ...r.extra,
});
