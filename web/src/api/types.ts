// Response shapes for the cancer-center API. These mirror the Polars frame
// schemas returned by cu_openalex.cancer_center.api / queries.py. Keep in sync
// with that module (or regenerate from /openapi.json with openapi-typescript).

export interface Meta {
  default_min_year: number;
  default_max_year: number;
  indexing_lag_from: number;
  current_programs: string[];
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
