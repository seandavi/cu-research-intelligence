// Response shapes for the cancer-center API. These mirror the Polars frame
// schemas returned by cu_openalex.cancer_center.api / queries.py. Keep in sync
// with that module (or regenerate from /openapi.json with openapi-typescript).

export interface Meta {
  default_min_year: number;
  default_max_year: number;
  indexing_lag_from: number;
  current_programs: string[];
  all_programs: string[];
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

export interface TopicRow {
  topic: string;
  publications: number;
  citations: number;
  mean_fwci: number | null;
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
