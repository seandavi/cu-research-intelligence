// Typed fetch client for the cancer-center API. Base URL defaults to "/api"
// (same-origin behind Traefik / via the Vite dev proxy); override with
// VITE_API_BASE for cross-origin deploys.
import type {
  ChatResponse,
  CollaborationTrendRow,
  CollaboratorRow,
  InterInstTrendRow,
  Kpi,
  MatrixCell,
  MemberProfile,
  MemberRow,
  Meta,
  NetworkData,
  PublicationFilters,
  PublicationResults,
  ProgramCombination,
  ProgramSummaryRow,
  PublicationYearRow,
  TopicRow,
  YearRange,
} from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function get<T>(path: string, params: Record<string, unknown> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) qs.set(k, String(v));
  }
  const url = `${BASE}${path}${qs.toString() ? `?${qs}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return res.json() as Promise<T>;
}

const yr = (r?: YearRange) =>
  r ? { min_year: r.minYear, max_year: r.maxYear } : {};

export const api = {
  meta: () => get<Meta>("/meta"),
  kpi: (r?: YearRange) => get<Kpi>("/kpi", yr(r)),
  publicationsByYear: (r?: YearRange, by?: "collaboration_class") =>
    get<PublicationYearRow[]>("/publications-by-year", { ...yr(r), by }),
  collaborationTrend: (r?: YearRange) =>
    get<CollaborationTrendRow[]>("/collaboration-trend", yr(r)),
  programSummary: (r?: YearRange, currentOnly = true) =>
    get<ProgramSummaryRow[]>("/program-summary", { ...yr(r), current_only: currentOnly }),
  collaborationMatrix: (r?: YearRange, currentOnly = true) =>
    get<MatrixCell[]>("/program-collaboration-matrix", { ...yr(r), current_only: currentOnly }),
  programCombinations: (r?: YearRange, currentOnly = true) =>
    get<ProgramCombination[]>("/program-combinations", { ...yr(r), current_only: currentOnly }),
  topTopics: (r?: YearRange, program?: string, fieldLevel = "topic_field", limit = 20) =>
    get<TopicRow[]>("/top-topics", { ...yr(r), program, field_level: fieldLevel, limit }),
  members: (r?: YearRange) => get<MemberRow[]>("/members", yr(r)),
  member: (id: number, r?: YearRange) => get<MemberProfile>(`/member/${id}`, yr(r)),
  publications: async (f: PublicationFilters): Promise<PublicationResults> => {
    const qs = new URLSearchParams();
    const set = (k: string, v: unknown) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    };
    set("q", f.q);
    set("min_year", f.minYear);
    set("max_year", f.maxYear);
    set("collaboration_class", f.collaboration_class);
    set("is_oa", f.is_oa);
    set("inter_institutional", f.inter_institutional);
    set("journal", f.journal);
    set("author", f.author);
    set("min_citations", f.min_citations);
    set("min_rcr", f.min_rcr);
    set("sort", f.sort);
    set("descending", f.descending);
    set("page", f.page);
    set("page_size", f.page_size);
    for (const p of f.programs ?? []) qs.append("programs", p);
    const res = await fetch(`${BASE}/publications?${qs}`);
    if (!res.ok) throw new Error(`publications search failed: ${res.status}`);
    return res.json() as Promise<PublicationResults>;
  },
  topCollaborators: (r?: YearRange, limit = 20) =>
    get<CollaboratorRow[]>("/top-collaborators", { ...yr(r), limit }),
  interInstTrend: (r?: YearRange) =>
    get<InterInstTrendRow[]>("/inter-institutional-trend", yr(r)),
  network: (r?: YearRange, minShared = 2, program?: string) =>
    get<NetworkData>("/network", { ...yr(r), min_shared: minShared, program }),
  chat: async (question: string, history?: unknown[]): Promise<ChatResponse> => {
    const res = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
    if (!res.ok) throw new Error(`chat failed: ${res.status}`);
    return res.json() as Promise<ChatResponse>;
  },
};
