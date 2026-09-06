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

export const useProgramSummary = (r?: YearRange, currentOnly = true, focus?: string) =>
  useQuery({
    queryKey: key("progsum", r, `${currentOnly}:${focus ?? ""}`),
    queryFn: () => api.programSummary(r, currentOnly, focus),
    enabled: !!r,
  });

export const useCollaborationMatrix = (r?: YearRange, currentOnly = true, focus?: string) =>
  useQuery({
    queryKey: key("matrix", r, `${currentOnly}:${focus ?? ""}`),
    queryFn: () => api.collaborationMatrix(r, currentOnly, focus),
    enabled: !!r,
  });

export const useProgramCombinations = (r?: YearRange, currentOnly = true) =>
  useQuery({
    queryKey: key("combos", r, currentOnly),
    queryFn: () => api.programCombinations(r, currentOnly),
    enabled: !!r,
  });

export const useMembers = (r?: YearRange, focus?: string, minFoci?: number) =>
  useQuery({
    queryKey: key("members", r, `${focus ?? ""}:${minFoci ?? ""}`),
    queryFn: () => api.members(r, focus, minFoci),
    enabled: !!r,
  });

export const useFociCombinations = (r?: YearRange) =>
  useQuery({ queryKey: key("foci_combos", r), queryFn: () => api.fociCombinations(r), enabled: !!r });

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

export const useNetwork = (r?: YearRange, minShared = 2, program?: string, focus?: string) =>
  useQuery({
    queryKey: key("network", r, `${minShared}:${program ?? ""}:${focus ?? ""}`),
    queryFn: () => api.network(r, minShared, program, focus),
    enabled: !!r,
  });

export const useMe = () =>
  useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: Infinity });

export const useRetreatThemes = (r?: YearRange) =>
  useQuery({ queryKey: key("retreat_themes", r), queryFn: () => api.retreatThemes(r), enabled: !!r });

export const useRetreatEntries = (enabled: boolean) =>
  useQuery({ queryKey: ["retreat_entries"], queryFn: api.retreatEntries, retry: false, enabled });

export const useRetreatThemeWorks = (theme: number, memberId: number | undefined, r?: YearRange) =>
  useQuery({
    queryKey: key("retreat_works", r, `${theme}:${memberId ?? ""}`),
    queryFn: () => api.retreatThemeWorks(theme, memberId, r),
    enabled: !!r && memberId !== undefined,
  });

export const useRetreatPeople = (theme: number, relativeTo: number | null | undefined, r?: YearRange) =>
  useQuery({
    queryKey: key("retreat_people", r, `${theme}:${relativeTo ?? ""}`),
    queryFn: () => api.retreatPeople(theme, relativeTo!, r),
    enabled: !!r && relativeTo != null,
  });
