"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { Company, ExportLogEntry, Project } from "@/lib/types";
import { SAMPLE_COMPANIES, SAMPLE_PROJECTS } from "@/lib/sampleData";
import { CompanyFilters, DEFAULT_FILTERS } from "@/lib/filters";
import { api, isBackendConfigured } from "@/lib/api/client";

/** A named set of filters the user saved on the Data Filters page. */
export interface FilterPreset {
  id: string;
  name: string;
  filters: CompanyFilters;
}

/**
 * loading: asking the backend for records; ready: backend answered (possibly with zero records);
 * error: backend unreachable (cached real records, if any, are shown); demo: backend disabled on purpose.
 */
export type DataStatus = "loading" | "ready" | "error" | "demo";

interface AppContextValue {
  /** Real records from the extraction backend. Sample records appear only in explicit demo mode. */
  companies: Company[];
  dataStatus: DataStatus;
  dataError: string | null;
  /** True only when the records on screen are the built-in invented samples. */
  isDemoData: boolean;
  reloadCompanies: () => Promise<void>;
  projects: Project[];
  addProject: (p: Project) => void;
  addCompanies: (companies: Company[]) => void;
  deleteProject: (id: string) => void;
  exportLog: ExportLogEntry[];
  addExportLog: (e: ExportLogEntry) => void;
  clearExportLog: () => void;
  filters: CompanyFilters;
  setFilters: (f: CompanyFilters | ((prev: CompanyFilters) => CompanyFilters)) => void;
  resetFilters: () => void;
  presets: FilterPreset[];
  savePreset: (name: string) => void;
  deletePreset: (id: string) => void;
  resetDemoData: () => void;
  toast: string | null;
  showToast: (message: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

const KEYS = {
  projects: "datamine-user-projects",
  exports: "datamine-export-log",
  presets: "datamine-filter-presets",
  extracted: "datamine-extracted-companies",
} as const;

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore: storage unavailable or full */
  }
}

function mergeCompanyRecords(records: Company[]): Company[] {
  const merged = new Map<string, Company>();
  for (const company of records) {
    const key = company.siren ? `${company.country}:${company.siren}` : company.id;
    const previous = merged.get(key);
    if (!previous) {
      merged.set(key, company);
      continue;
    }
    merged.set(key, {
      ...previous,
      ...company,
      director: company.director || previous.director,
      email: company.email || previous.email,
      phone: company.phone || previous.phone,
      employees: company.employees || previous.employees,
      employeeBand: company.employeeBand || previous.employeeBand,
      turnover: company.turnover || previous.turnover,
      turnoverYear: company.turnoverYear || previous.turnoverYear,
      address: company.address || previous.address,
      website: company.website || previous.website,
      b2cWebsite: company.b2cWebsite || previous.b2cWebsite,
      b2cWebsiteStatus: company.b2cWebsite || previous.b2cWebsite
        ? "found"
        : company.b2cWebsiteStatus || previous.b2cWebsiteStatus,
    });
  }
  return Array.from(merged.values());
}

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [userProjects, setUserProjects] = useState<Project[]>([]);
  const [extractedCompanies, setExtractedCompanies] = useState<Company[]>([]);
  const [exportLog, setExportLog] = useState<ExportLogEntry[]>([]);
  const [presets, setPresets] = useState<FilterPreset[]>([]);
  const [filters, setFilters] = useState<CompanyFilters>(DEFAULT_FILTERS);
  const [toast, setToast] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [dataStatus, setDataStatus] = useState<DataStatus>(isBackendConfigured() ? "loading" : "demo");
  const [dataError, setDataError] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * The backend database is the source of truth. A successful response REPLACES the
   * browser cache (the cache is only an offline fallback). Nothing is deleted server-side.
   */
  const reloadCompanies = useCallback(async () => {
    if (!isBackendConfigured()) {
      setDataStatus("demo");
      return;
    }
    setDataStatus("loading");
    setDataError(null);
    try {
      const { companies } = await api.getCompanies();
      const real = (Array.isArray(companies) ? companies : []).filter((c) => c.origin !== "sample");
      setExtractedCompanies(mergeCompanyRecords(real));
      setDataStatus("ready");
    } catch (error) {
      setDataError(error instanceof Error ? error.message : "Could not load records from the extraction service.");
      setDataStatus("error");
    }
  }, []);

  // Load saved data once, in the browser only (avoids server/browser mismatch)
  useEffect(() => {
    setUserProjects(load<Project[]>(KEYS.projects, []));
    setExportLog(load<ExportLogEntry[]>(KEYS.exports, []));
    setPresets(load<FilterPreset[]>(KEYS.presets, []));
    // Cached records are shown while the backend loads, but invented samples are never accepted from the cache.
    setExtractedCompanies(
      mergeCompanyRecords(load<Company[]>(KEYS.extracted, []).filter((c) => c.origin !== "sample"))
    );
    setLoaded(true);
    void reloadCompanies();
  }, [reloadCompanies]);

  useEffect(() => {
    if (loaded) save(KEYS.projects, userProjects);
  }, [userProjects, loaded]);
  useEffect(() => {
    if (loaded) save(KEYS.exports, exportLog);
  }, [exportLog, loaded]);
  useEffect(() => {
    if (loaded) save(KEYS.presets, presets);
  }, [presets, loaded]);
  useEffect(() => {
    if (loaded) save(KEYS.extracted, extractedCompanies);
  }, [extractedCompanies, loaded]);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  }, []);

  const addProject = useCallback((p: Project) => setUserProjects((prev) => [p, ...prev]), []);
  const addCompanies = useCallback((records: Company[]) => setExtractedCompanies((prev) => mergeCompanyRecords([...records, ...prev])), []);
  const deleteProject = useCallback((id: string) => setUserProjects((prev) => prev.filter((p) => p.id !== id)), []);
  const addExportLog = useCallback((e: ExportLogEntry) => setExportLog((prev) => [e, ...prev].slice(0, 100)), []);
  const clearExportLog = useCallback(() => setExportLog([]), []);
  const resetFilters = useCallback(() => setFilters(DEFAULT_FILTERS), []);

  const savePreset = useCallback(
    (name: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      setPresets((prev) => [{ id: `preset-${Date.now()}`, name: trimmed, filters }, ...prev].slice(0, 20));
    },
    [filters]
  );
  const deletePreset = useCallback((id: string) => setPresets((prev) => prev.filter((p) => p.id !== id)), []);

  const resetDemoData = useCallback(() => {
    setUserProjects([]);
    setExportLog([]);
    setPresets([]);
    setFilters(DEFAULT_FILTERS);
  }, []);

  const projects = useMemo(() => (userProjects.length > 0 ? userProjects : SAMPLE_PROJECTS), [userProjects]);

  // Samples are used only when the backend is disabled on purpose (demo mode) and nothing real exists.
  const companies = useMemo(
    () => (isBackendConfigured() ? extractedCompanies : extractedCompanies.length > 0 ? extractedCompanies : SAMPLE_COMPANIES),
    [extractedCompanies]
  );
  const isDemoData = companies.length > 0 && companies.every((c) => c.origin === "sample");

  const value = useMemo<AppContextValue>(
    () => ({
      companies,
      dataStatus,
      dataError,
      isDemoData,
      reloadCompanies,
      projects,
      addProject,
      addCompanies,
      deleteProject,
      exportLog,
      addExportLog,
      clearExportLog,
      filters,
      setFilters,
      resetFilters,
      presets,
      savePreset,
      deletePreset,
      resetDemoData,
      toast,
      showToast,
    }),
    [
      companies, dataStatus, dataError, isDemoData, reloadCompanies, projects, addProject, addCompanies, deleteProject, exportLog,
      addExportLog, clearExportLog, filters, resetFilters, presets, savePreset, deletePreset, resetDemoData, toast, showToast,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
