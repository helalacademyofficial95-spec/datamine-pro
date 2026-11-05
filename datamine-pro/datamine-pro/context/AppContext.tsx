"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { Company, ExportLogEntry, Project } from "@/lib/types";
import { SAMPLE_COMPANIES, SAMPLE_PROJECTS } from "@/lib/sampleData";
import { CompanyFilters, DEFAULT_FILTERS } from "@/lib/filters";

/** A named set of filters the user saved on the Data Filters page. */
export interface FilterPreset {
  id: string;
  name: string;
  filters: CompanyFilters;
}

interface AppContextValue {
  /** All company records currently available. In v1 these are all SAMPLE records. */
  companies: Company[];
  projects: Project[];
  addProject: (p: Project) => void;
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

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [userProjects, setUserProjects] = useState<Project[]>([]);
  const [exportLog, setExportLog] = useState<ExportLogEntry[]>([]);
  const [presets, setPresets] = useState<FilterPreset[]>([]);
  const [filters, setFilters] = useState<CompanyFilters>(DEFAULT_FILTERS);
  const [toast, setToast] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load saved data once, in the browser only (avoids server/browser mismatch)
  useEffect(() => {
    setUserProjects(load<Project[]>(KEYS.projects, []));
    setExportLog(load<ExportLogEntry[]>(KEYS.exports, []));
    setPresets(load<FilterPreset[]>(KEYS.presets, []));
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (loaded) save(KEYS.projects, userProjects);
  }, [userProjects, loaded]);
  useEffect(() => {
    if (loaded) save(KEYS.exports, exportLog);
  }, [exportLog, loaded]);
  useEffect(() => {
    if (loaded) save(KEYS.presets, presets);
  }, [presets, loaded]);

  const showToast = useCallback((message: string) => {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  }, []);

  const addProject = useCallback((p: Project) => setUserProjects((prev) => [p, ...prev]), []);
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

  const projects = useMemo(() => [...userProjects, ...SAMPLE_PROJECTS], [userProjects]);

  const value = useMemo<AppContextValue>(
    () => ({
      companies: SAMPLE_COMPANIES,
      projects,
      addProject,
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
      projects, addProject, deleteProject, exportLog, addExportLog, clearExportLog, filters, resetFilters,
      presets, savePreset, deletePreset, resetDemoData, toast, showToast,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
