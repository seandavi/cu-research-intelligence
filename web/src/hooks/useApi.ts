import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { PublicationFilters, YearRange } from "../api/types";

const key = (name: string, r?: YearRange, extra?: unknown) => [name, r?.minYear, r?.maxYear, extra];

export const useMeta = () => useQuery({ queryKey: ["meta"], queryFn: api.meta, staleTime: Infinity });

export const useKpi = (r?: YearRange) =>
  useQuery({ queryKey: key("kpi", r), queryFn: () => api.kpi(r), enabled: !!r });

export const usePublicationsByYear = (r?: YearRange, by?: "collaboration_class") =>
  useQuery({ queryKey: key("pubs", r, by), queryFn: () => api.publicationsByYear(r, by), enabled: !!r });

export const useCollaborationTrend = (r?: YearRange) =>
  useQuery({ queryKey: key("trend", r), queryFn: () => api.collaborationTrend(r), enabled: !!r });

export const useProgramSummary = (r?: YearRange, currentOnly = true) =>
  useQuery({
    queryKey: key("progsum", r, currentOnly),
    queryFn: () => api.programSummary(r, currentOnly),
    enabled: !!r,
  });

export const useCollaborationMatrix = (r?: YearRange, currentOnly = true) =>
  useQuery({
    queryKey: key("matrix", r, currentOnly),
    queryFn: () => api.collaborationMatrix(r, currentOnly),
    enabled: !!r,
  });

export const useProgramCombinations = (r?: YearRange, currentOnly = true) =>
  useQuery({
    queryKey: key("combos", r, currentOnly),
    queryFn: () => api.programCombinations(r, currentOnly),
    enabled: !!r,
  });

export const useMembers = (r?: YearRange) =>
  useQuery({ queryKey: key("members", r), queryFn: () => api.members(r), enabled: !!r });

export const usePublications = (filters: PublicationFilters) =>
  useQuery({
    queryKey: ["publications", filters],
    queryFn: () => api.publications(filters),
    placeholderData: keepPreviousData, // keep the table visible while paging/filtering
  });

export const useTopCollaborators = (r?: YearRange, limit = 20) =>
  useQuery({
    queryKey: key("collab", r, limit),
    queryFn: () => api.topCollaborators(r, limit),
    enabled: !!r,
  });

export const useInterInstTrend = (r?: YearRange) =>
  useQuery({ queryKey: key("iitrend", r), queryFn: () => api.interInstTrend(r), enabled: !!r });

export const useGrantsSummary = (r?: YearRange) =>
  useQuery({ queryKey: key("grant_sum", r), queryFn: () => api.grantsSummary(r), enabled: !!r });

export const useGrantsByProgram = (r?: YearRange) =>
  useQuery({ queryKey: key("grant_prog", r), queryFn: () => api.grantsByProgram(r), enabled: !!r });

export const useGrantsByAgency = (r?: YearRange) =>
  useQuery({ queryKey: key("grant_agency", r), queryFn: () => api.grantsByAgency(r), enabled: !!r });

export const useMemberProfile = (id: number | undefined, r?: YearRange) =>
  useQuery({
    queryKey: key("member", r, id),
    queryFn: () => api.member(id!, r),
    enabled: !!r && id !== undefined,
  });

export const useMemberLinks = (id: number | undefined, linkType?: string) =>
  useQuery({
    queryKey: key("member_links", undefined, `${id}:${linkType ?? ""}`),
    queryFn: () => api.memberLinks(id!, linkType),
    enabled: id !== undefined,
  });

export const useNetwork = (r?: YearRange, minShared = 2, program?: string) =>
  useQuery({
    queryKey: key("network", r, `${minShared}:${program ?? ""}`),
    queryFn: () => api.network(r, minShared, program),
    enabled: !!r,
  });
