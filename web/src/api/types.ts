// Response shapes for the cancer-center API. These mirror the Polars frame
// schemas returned by cu_openalex.cancer_center.api / queries.py. Keep in sync
// with that module (or regenerate from /openapi.json with openapi-typescript).

export interface Meta {
  default_min_year: number;
  default_max_year: number;
  indexing_lag_from: number;
  current_programs: string[];
  all_programs: string[];
  grants_available: boolean;
  /** Freshness stamps baked into the serving DB (see cancer_center.bake). */
  data_freshness: Record<string, string>;
}

export interface MemberGrant {
  core_project_num: string;
  activity_code: string | null;
  agency: string | null;
  latest_fy: number;
  title: string | null;
  total_award: number | null;
  is_contact_pi: boolean;
  is_active: boolean;
}

export interface GrantSummary {
  grants: number;
  funded_members: number;
  total_award: number | null;
  r01_grants: number;
}

export interface GrantProgramRow {
  program: string;
  grants: number;
  funded_members: number;
  total_award: number | null;
}

export interface GrantAgencyRow {
  agency: string;
  grants: number;
  total_award: number | null;
}

export interface PublicationRow {
  work_id: string;
  title: string | null;
  snippet: string | null;
  publication_year: number;
  doi: string | null;
  pmid: string | null;
  type: string | null;
  source_name: string | null;
  cited_by_count: number | null;
  fwci: number | null;
  rcr: number | null;
  is_oa: boolean;
  oa_status: string | null;
  primary_topic: string | null;
  topic_field: string | null;
  programs: string[];
  collaboration_class: string;
  has_external_collab: boolean;
  is_international: boolean;
}

export interface PublicationFilters {
  q?: string;
  minYear?: number;
  maxYear?: number;
  programs?: string[];
  collaboration_class?: string;
  is_oa?: boolean;
  inter_institutional?: boolean;
  journal?: string;
  author?: string;
  min_citations?: number;
  min_rcr?: number;
  sort?: string;
  descending?: boolean;
  page?: number;
  page_size?: number;
}

export interface PublicationResults {
  total: number;
  page: number;
  page_size: number;
  rows: PublicationRow[];
}

export interface Kpi {
  publications: number;
  citations: number;
  mean_fwci: number | null;
  median_fwci: number | null;
  median_rcr: number | null;
  n_with_rcr: number | null;
  pct_open_access: number;
  pct_collaborative: number;
  n_collaborative: number;
  pct_inter_program: number;
  pct_intra_program: number;
  pct_inter_institutional: number;
  pct_international: number;
  high_impact_fwci2: number;
  members_all: number;
  members_active: number;
  members_resolved: number;
  active_resolved: number;
}

export type CollaborationClass = "solo" | "intra_program" | "inter_program";

export interface PublicationYearRow {
  publication_year: number;
  collaboration_class?: CollaborationClass;
  publications: number;
  citations: number;
  mean_fwci?: number | null;
}

export interface CollaborationTrendRow {
  publication_year: number;
  pct_intra: number;
  pct_inter: number;
  pct_solo: number;
  publications: number;
}

export interface ProgramSummaryRow {
  program: string;
  publications: number;
  citations: number;
  mean_fwci: number | null;
  median_rcr: number | null;
  pct_inter_program: number;
  pct_intra_program: number;
}

export interface MatrixCell {
  prog_a: string;
  prog_b: string;
  publications: number;
}

export interface ProgramCombination {
  programs: string[];
  count: number;
}

export interface MemberRow {
  member_id: number;
  name: string;
  program: string;
  rank: string;
  status: string;
  match_confidence: string | null;
  publications: number;
  citations: number | null;
  mean_fwci: number | null;
}

export interface ChatResponse {
  answer: string;
  queries: string[];
  table: Record<string, unknown>[] | null;
  suggestions: string[];
  error: string | null;
}

export interface CollaboratorRow {
  institution: string;
  country: string | null;
  publications: number;
}

export interface InterInstTrendRow {
  publication_year: number;
  pct_inter_institutional: number;
  pct_international: number;
  publications: number;
}

// Membership spine (ADR-0025) detail carried on the member profile.
export interface MemberIdentifier {
  id_type: string;
  id_value: string;
  source: string;
  is_primary: boolean;
}

export interface MemberMembership {
  snapshot_date: string;
  program: string | null;
  short_code: string | null;
  member_type: string | null;
  member_status: string | null;
  status_date: string | null;
  member_type_start_date: string | null;
  applied_date: string | null;
  is_active: boolean;
}

export interface LifecycleEvent {
  event_type: string;
  event_date: string;
  detail: string | null;
}

export interface LinkCount {
  link_type: string;
  n: number;
  total_weight: number;
}

export interface MemberSpine {
  identifiers: MemberIdentifier[];
  membership: MemberMembership[];
  appointment: { faculty_rank: string | null; org_path: string | null };
  lifecycle: LifecycleEvent[];
  link_counts: LinkCount[];
}

export interface MemberLink {
  other_member_id: number;
  other_name: string | null;
  other_program: string | null;
  link_type: string;
  weight: number;
  min_year: number;
  max_year: number;
}

export interface MemberProfile {
  member: {
    member_id: number;
    name: string;
    program: string;
    rank: string;
    status: string;
    dept: string;
    school: string;
    email: string;
    match_confidence: string | null;
    author_id: string | null;
    orcid: string | null;
  };
  summary: {
    publications: number;
    citations: number | null;
    mean_fwci: number | null;
    median_rcr: number | null;
    pct_open_access: number | null;
  };
  by_year: { publication_year: number; publications: number; citations: number }[];
  top_topics: { topic: string; publications: number }[];
  top_journals: { journal: string; publications: number }[];
  top_coauthors: { member_id: number; name: string; program: string; shared: number }[];
  grants: MemberGrant[];
  spine: MemberSpine | null;
}

export interface NetworkNode {
  id: number;
  name: string;
  program: string;
  publications: number;
  degree: number;
  betweenness: number;
}

export interface NetworkEdge {
  source: number;
  target: number;
  weight: number;
}

export interface NetworkData {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
}

export interface YearRange {
  minYear: number;
  maxYear: number;
}

// --- Scientific retreat -----------------------------------------------------

export interface RetreatTheme {
  name: string;
  group: string;
  terms: string[];
  how: string;
  footnote: boolean;
  publications: number;
  keyword_hits: number;
  active_publications: number;
  inter_program_pct: number;
  members: number;
  by_year: { year: number; publications: number }[];
  by_program: { program: string; publications: number }[];
  pairs: { a: string; b: string; publications: number }[];
  top_members: {
    member_id: number;
    name: string;
    program: string | null;
    publications: number;
    match_confidence: string | null;
    rank: string | null;
    joined_year: number | null;
    early_career: boolean;
  }[];
  top_topics: { topic: string; publications: number }[];
}

export interface RetreatReport {
  window: { min_year: number; max_year: number };
  denominator: {
    member_publications: number;
    cancer_relevant: number | null;
    cancer_filter: boolean;
    active_members: number;
    active_members_resolved: number;
  };
  themes: RetreatTheme[];
}

export interface RetreatWork {
  work_id: string;
  title: string;
  publication_year: number;
  source_name: string | null;
  collaboration_class: string | null;
  rcr: number | null;
  doi: string | null;
  programs: string[];
}

export interface RetreatPerson {
  member_id: number;
  name: string;
  program: string | null;
  publications: number;
  top_topic: string | null;
  early_career: boolean;
}

export type RetreatKind = "abstract" | "question" | "registration";

export interface RetreatEntry {
  id: number;
  kind: RetreatKind;
  source_id: string | null;
  name: string;
  email: string | null;
  member_id: number | null;
  program: string | null;
  role: string | null;
  title: string | null;
  body: string | null;
  category: string | null;
  decision: string | null;
  decided_by: string | null;
  decided_at: string | null;
  extra: Record<string, string>;
  import_file: string | null;
  imported_at: string | null;
  created_at: string;
  updated_at: string;
  themes: string[];
  mine: boolean;
}

export interface RetreatEntries {
  organizer: boolean;
  entries: RetreatEntry[];
}

export interface Me {
  authenticated: boolean;
  user_id?: number;
  email?: string;
  name?: string | null;
  member_id?: number | null;
  roles?: string[];
}
