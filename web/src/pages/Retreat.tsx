import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { RetreatEntry, RetreatTheme, RetreatWork, YearRange } from "../api/types";
import { Card, ErrorNote, KpiCard, Loading } from "../components/ui";
import {
  useMe,
  useMeta,
  useRetreatEntries,
  useRetreatPeople,
  useRetreatThemeWorks,
  useRetreatThemes,
} from "../hooks/useApi";
import { downloadCsv, fmtInt, fmtNum, fmtPct } from "../lib/format";

const RETREAT_DATE = "2026-11-20";
const ABSTRACT_DEADLINE = "2026-09-14";
// The announcement's forms live outside this app; set when the URLs are known.
const RETREAT_INFO_URL =
  "https://medschool.cuanschutz.edu/colorado-cancer-center/research/cancer-center-scientific-retreat";
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
const EC = <span className="badge ec" title="Assistant professor / instructor, or joined 2020 or later">early-career</span>;
const daysUntil = (iso: string) => Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
const short = (p: string | null) => (p ?? "").split(" ").map((w) => w[0]).join("");
const fmtDate = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

export function Retreat({ range }: { range: YearRange }) {
  const meta = useMeta();
  const me = useMe();
  const report = useRetreatThemes(range);
  const signedIn = me.data?.authenticated === true;
  const entries = useRetreatEntries(signedIn);
  const [sel, setSel] = useState(0);
  const [showHow, setShowHow] = useState(false);

  const programs = [...(meta.data?.current_programs ?? [])].sort();
  const organizer = entries.data?.organizer ?? false;
  const rows = entries.data?.entries ?? [];
  const abstracts = rows.filter((r) => r.kind === "abstract");
  const deadline = daysUntil(ABSTRACT_DEADLINE);

  if (report.isLoading) return <Loading />;
  if (report.error) return <ErrorNote error={report.error} />;
  const { themes, denominator: d, window } = report.data!;
  const cur = themes[sel];

  return (
    <>
      <h1>Scientific Retreat 2026 — Advancing Our Strategic Vision</h1>
      <p className="lede">
        November 20, 2026. Keynote <em>The Future of Cancer Clinical Trials</em> (Razelle Kurzrock,
        MD), then a panel with clinical-trial leaders. Abstracts should reflect the Strategic
        Plan's five scientific foci; this page shows which members already publish in each focus
        and how far that work crosses programs, so sessions can be built around real strengths
        and real gaps — and it collects abstracts, panel questions, and registrations.
      </p>

      <Card title="Take part" action={null}>
        <div className="cta-body">
          <ul>
            <li>
              <strong>Abstracts</strong> — due <strong>September 14, 5:00 pm</strong>
              {deadline >= 0 ? ` (${deadline} days)` : " (closed)"}; decisions October 21. Members and
              their trainees, fellows and research staff; main-room oral, concurrent targeted-discussion
              session, or poster. Priority to new impact, cross-program collaboration, translational
              potential, unmet clinical or population needs, and use of shared resources.
              {RETREAT_INFO_URL && (
                <>
                  {" "}
                  <a href={RETREAT_INFO_URL}>Guidelines &amp; forms</a>
                </>
              )}
            </li>
            <li>
              <strong>Panel questions</strong> — on the Future of Cancer Clinical Trials only.{" "}
              {signedIn ? "Submit below." : <a href="/api/auth/login">Sign in to submit one.</a>}
            </li>
            <li>
              <strong>Registration</strong> — via the Retreat Registration form.{" "}
              {signedIn ? "Your submissions and their status appear below." : (
                <a href="/api/auth/login">Sign in to see your submissions.</a>
              )}
            </li>
          </ul>
        </div>
      </Card>

      <div className="kpi-row">
        <KpiCard
          label={`Cancer-relevant member publications, ${window.min_year}–${window.max_year}`}
          value={d.cancer_relevant != null ? fmtInt(d.cancer_relevant) : fmtInt(d.member_publications)}
          hint={`of ${fmtInt(d.member_publications)} peer-reviewed member publications in the window`}
        />
        <KpiCard
          label="Active members (resolved to OpenAlex)"
          value={`${fmtInt(d.active_members_resolved)} / ${fmtInt(d.active_members)}`}
          hint="Only resolved members can appear in theme counts"
        />
        <KpiCard
          label={organizer ? "Abstracts submitted" : "Your submissions"}
          value={signedIn ? fmtInt(organizer ? abstracts.length : rows.filter((r) => r.mine).length) : "Sign in"}
        />
        <KpiCard
          label={deadline >= 0 ? "Days to abstract deadline" : "Days to retreat"}
          value={fmtInt(deadline >= 0 ? deadline : daysUntil(RETREAT_DATE))}
          hint={`Abstracts due ${ABSTRACT_DEADLINE}; retreat ${RETREAT_DATE}`}
        />
      </div>

      <Card
        title={`Retreat themes across member publications (${window.min_year}–${window.max_year})`}
        action={
          <span>
            <button onClick={() => setShowHow((v) => !v)}>{showHow ? "Hide" : "Show"} how counted</button>{" "}
            <button onClick={() => downloadCsv(themeCsv(themes, programs), "uccc_retreat_themes.csv")}>⬇ CSV</button>
          </span>
        }
      >
        <table className="data compact">
          <thead>
            <tr>
              <th>Theme</th>
              <th className="num">Publications</th>
              <th className="num" title="Share of the theme's publications with members from ≥2 programs">
                Inter-program
              </th>
              <th className="num" title="Active members with ≥1 publication in the theme">Members</th>
              {programs.map((p) => (
                <th key={p} className="num" title={p}>
                  {short(p)}
                </th>
              ))}
              <th title="Publications per year across the window">Trend</th>
              {organizer && (
                <>
                  <th className="num" title="Submitted abstracts whose title/text matches the theme">Abstracts</th>
                  <th className="num">Oral</th>
                  <th className="num">Disc.</th>
                  <th className="num">Poster</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {themes.map((th, i) => (
              <>
                {(i === 0 || themes[i - 1].group !== th.group) && (
                  <tr key={th.group}>
                    <td colSpan={6 + programs.length + (organizer ? 4 : 0)} className="muted group">{th.group}</td>
                  </tr>
                )}
              <tr key={th.name} className={`clickable ${i === sel ? "sel" : ""} ${th.footnote ? "muted" : ""}`} onClick={() => setSel(i)}>
                <td>
                  {th.name}
                  {th.footnote && <span className="termlist"> (topic signal only)</span>}
                  {showHow && (
                    <div className="termlist">
                      {th.terms.length ? th.terms.join(" · ") + (th.how.startsWith("any term") ? "" : ` — ${th.how}`) : th.how}
                    </div>
                  )}
                </td>
                <td className="num">
                  {fmtInt(th.publications)}
                  <div className="termlist" title="Keyword hits before the cancer-relevance filter · counted works with a current member author">
                    of {fmtInt(th.keyword_hits)} hits · {fmtInt(th.active_publications)} current
                  </div>
                </td>
                <td className="num">{fmtPct(th.inter_program_pct)}</td>
                <td className="num">{fmtInt(th.members)}</td>
                {programs.map((p) => (
                  <td key={p} className="num">
                    {fmtInt(th.by_program.find((b) => b.program === p)?.publications ?? 0)}
                  </td>
                ))}
                <td>
                  <Spark data={th.by_year} />
                </td>
                {organizer && (
                  <>
                    <td className="num">{fmtInt(abstracts.filter((a) => a.themes.includes(th.name)).length)}</td>
                    {["oral", "discussion", "poster"].map((d) => (
                      <td key={d} className="num">
                        {fmtInt(abstracts.filter((a) => a.themes.includes(th.name) && a.decision === d).length)}
                      </td>
                    ))}
                  </>
                )}
              </tr>
              </>
            ))}
          </tbody>
        </table>
        <p className="caveat">
          <strong>How to read this.</strong> The five foci are the Strategic Plan's, as quoted on
          the retreat page; the trial themes follow the keynote. A publication counts toward a focus
          when its title or abstract contains one of its terms (word-start match); a{" "}
          <em>clinical trial report</em> must name a trial phase or design in its title or cite an
          NCT id, and reviews are excluded. These are provisional keyword sets, not a classification
          of the science. Investigator-initiated status, PI-ship and accrual are not in publication
          data (CTO/OnCore, ClinicalTrials.gov — not yet loaded).{" "}
          {d.cancer_filter
            ? "Only publications the deterministic cancer-relevance labeler (ADR-0027) marks cancer-relevant are counted — a high-precision, lower-bound set. "
            : "The cancer-relevance labeler is not baked into this deployment; all member publications are counted. "}
          A member's paper counts only if they were a Center member when it was published, so a
          recruit's earlier work elsewhere is not Center output. <em>Hits</em> is the keyword match
          before the cancer filter; retention differs by focus (lowest for basic-science
          vocabulary), so compare rows with that in mind. <em>Current</em> counts works with at
          least one currently active member author. Meeting abstracts are excluded.
          Program columns count a publication under every current program with a member author,
          so they can add to more than the total; legacy programs are omitted. <em>Members</em> are
          active members only; {fmtInt(d.active_members - d.active_members_resolved)} active members
          are not yet matched to OpenAlex and cannot appear. Recent years are provisional (indexing
          lag). Click a theme for members, program pairs, topics, and the papers behind each count.
        </p>
      </Card>

      {cur && (
        <ThemeDetail theme={cur} index={sel} range={range} programs={programs} myMemberId={me.data?.member_id ?? null} minYear={window.min_year} />
      )}

      {!signedIn ? (
        <Card title="Submissions">
          <p className="muted">
            Abstracts, panel questions, and registrations are visible to signed-in CU Anschutz
            users (your own) and to the retreat committee (all).{" "}
            {me.error ? (
              <span>The submissions store is not enabled on this deployment.</span>
            ) : (
              <a href="/api/auth/login">Sign in</a>
            )}
          </p>
        </Card>
      ) : entries.error ? (
        <ErrorNote error={entries.error} />
      ) : organizer ? (
        <>
          <Abstracts rows={abstracts} />
          <Questions rows={rows.filter((r) => r.kind === "question")} organizer />
          <Registrations rows={rows.filter((r) => r.kind === "registration")} programs={programs} />
        </>
      ) : (
        <>
          <Mine rows={rows.filter((r) => r.mine)} />
          <Questions rows={rows.filter((r) => r.kind === "question")} organizer={false} />
        </>
      )}
    </>
  );
}

function Spark({ data }: { data: { year: number; publications: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.publications));
  return (
    <span className="spark" title={data.map((d) => `${d.year}: ${d.publications}`).join(", ")}>
      {data.map((d) => (
        <i key={d.year} style={{ height: `${Math.max(2, (18 * d.publications) / max)}px` }} />
      ))}
    </span>
  );
}

function ThemeDetail({
  theme, index, range, programs, myMemberId, minYear,
}: { theme: RetreatTheme; index: number; range: YearRange; programs: string[]; myMemberId: number | null; minYear: number }) {
  const [member, setMember] = useState<number | undefined>();
  const [showMine, setShowMine] = useState(false);
  const works = useRetreatThemeWorks(index, member, range);
  const mine = useRetreatThemeWorks(index, myMemberId ?? undefined, range);
  const people = useRetreatPeople(index, myMemberId, range);
  const shown = theme.top_members.find((m) => m.member_id === member);
  const noList = theme.top_members.length === 0 || theme.top_members[0].publications < 2;
  return (
    <>
      {myMemberId != null && (
        <Card title={`You in this theme — ${theme.name}`}>
          {mine.isLoading ? <Loading /> : (
            <p className="muted">
              {(mine.data ?? []).length === 0
                ? "None of your counted papers matches this theme's terms in the selected years."
                : <>{(mine.data ?? []).length} of your papers match. <a href="#" onClick={(e) => { e.preventDefault(); setShowMine((v) => !v); }}>{showMine ? "Hide" : "Show"}</a></>}
            </p>
          )}
          {showMine && <WorkList works={mine.data ?? []} />}
        </Card>
      )}

      <div className="grid3">
        <Card title="Current members with the most matching papers">
          {noList && <p className="muted">Too few matching papers per member to rank anyone; use the theme's paper list instead.</p>}
          <table className="data compact" hidden={noList}>
            <tbody>
              {theme.top_members.map((m) => (
                <tr key={m.member_id} className={`clickable ${m.member_id === member ? "sel" : ""}`} onClick={() => setMember(m.member_id === member ? undefined : m.member_id)}>
                  <td>
                    <Link to={`/members/${m.member_id}`} onClick={(e) => e.stopPropagation()}>{m.name}</Link>
                    {m.match_confidence !== "high" && (
                      <span className="badge medium" title="Name-based OpenAlex match (no ORCID); papers may include a namesake's">?</span>
                    )}
                    {m.early_career && EC}
                    <div className="termlist">
                      {m.rank ?? ""}{m.joined_year ? ` · member since ${m.joined_year}` : ""}
                      {m.joined_year && m.joined_year > minYear ? " (joined inside the window)" : ""}
                    </div>
                  </td>
                  <td className="muted">{short(m.program)}</td>
                  <td className="num">{fmtInt(m.publications)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">Click a name to see the papers behind the count. ? = name-based match without ORCID.</p>
        </Card>
        <Card title="Program pairs (joint publications)">
          <table className="data compact">
            <tbody>
              {theme.pairs.map((p) => (
                <tr key={`${p.a}|${p.b}`}>
                  <td>
                    {short(p.a)} × {short(p.b)}
                  </td>
                  <td className={`num ${p.publications === 0 ? "zero" : ""}`}>
                    {p.publications === 0 ? "none yet" : fmtInt(p.publications)}
                    {p.publications > 0 && theme.publications > 0 && (
                      <span className="termlist"> · {fmtPct((100 * p.publications) / theme.publications)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">
            Pairs with none yet are where a targeted discussion session could seed new
            collaboration. Programs: {programs.map((p) => `${short(p)} = ${p}`).join("; ")}.
          </p>
        </Card>
        <Card title="OpenAlex topics in this theme">
          <table className="data compact">
            <tbody>
              {theme.top_topics.map((x) => (
                <tr key={x.topic}>
                  <td>{x.topic}</td>
                  <td className="num">{fmtInt(x.publications)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {shown && (
        <Card title={`${shown.name}: ${theme.name} publications (${range.minYear}–${range.maxYear})`}>
          {works.isLoading ? <Loading /> : <WorkList works={works.data ?? []} />}
        </Card>
      )}

      {myMemberId != null && (
        <Card title={`People to meet at the retreat — ${theme.name}`}>
          {people.isLoading ? <Loading /> : (people.data ?? []).length === 0 ? (
            <p className="muted">No one outside your program and your existing collaborators publishes in this theme.</p>
          ) : (
            <table className="data compact">
              <tbody>
                {(people.data ?? []).map((p) => (
                  <tr key={p.member_id}>
                    <td>
                      <Link to={`/members/${p.member_id}`}>{p.name}</Link>
                      {p.early_career && EC}
                    </td>
                    <td className="muted">{short(p.program)}</td>
                    <td className="muted">{p.top_topic ?? ""}</td>
                    <td className="num">{fmtInt(p.publications)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted">Active members in other programs you have not co-authored or co-held a grant with, with at least two matching papers and their most frequent topic in the theme.</p>
        </Card>
      )}
    </>
  );
}

function WorkList({ works }: { works: RetreatWork[] }) {
  return (
    <ol className="worklist">
      {works.map((w) => (
        <li key={w.work_id}>
          {w.doi ? <a href={`https://doi.org/${w.doi}`} target="_blank" rel="noreferrer">{w.title}</a> : w.title}{" "}
          <span className="muted">
            {w.source_name ?? ""} {w.publication_year}
            {w.rcr != null ? ` · RCR ${fmtNum(w.rcr, 1)}` : ""}
            {w.programs.length > 1 ? ` · ${w.programs.map(short).join(" + ")}` : ""}
          </span>
        </li>
      ))}
    </ol>
  );
}

function themeCsv(t: RetreatTheme[], programs: string[]) {
  return t.map((th) => ({
    theme: th.name,
    publications: th.publications,
    inter_program_pct: th.inter_program_pct,
    members: th.members,
    ...Object.fromEntries(programs.map((p) => [p, th.by_program.find((b) => b.program === p)?.publications ?? 0])),
    ...Object.fromEntries(th.pairs.map((p) => [`${short(p.a)}x${short(p.b)}`, p.publications])),
    keyword_hits: th.keyword_hits,
    by_current_members: th.active_publications,
  }));
}

function Mine({ rows }: { rows: RetreatEntry[] }) {
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

function Abstracts({ rows }: { rows: RetreatEntry[] }) {
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
                <td className="muted">{short(r.program) || "—"}</td>
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

function Questions({ rows, organizer }: { rows: RetreatEntry[]; organizer: boolean }) {
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
                  <span className="muted"> — {r.mine && !organizer ? "you" : r.name}{r.program ? `, ${short(r.program)}` : ""}</span>
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

function Registrations({ rows, programs }: { rows: RetreatEntry[]; programs: string[] }) {
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
