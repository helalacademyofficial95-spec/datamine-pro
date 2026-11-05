import type { Company, ExtractionJob, ExtractionRequest, JobResults } from "./types";

/**
 * Tiny API client for the future Python backend.
 * While NEXT_PUBLIC_API_URL is empty, the app runs in demo mode and never calls any server.
 */
const BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export const isBackendConfigured = (): boolean => BASE_URL.length > 0;
export const getBackendUrl = (): string => BASE_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!isBackendConfigured()) {
    throw new Error("Backend not configured. Set NEXT_PUBLIC_API_URL in .env.local.");
  }
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) throw new Error(`Backend error ${response.status}`);
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: "ok" }>("/health"),
  createJob: (body: ExtractionRequest) =>
    request<ExtractionJob>("/jobs", { method: "POST", body: JSON.stringify(body) }),
  getJob: (id: string) => request<ExtractionJob>(`/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id: string) => request<ExtractionJob>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  getResults: (id: string) => request<JobResults>(`/jobs/${encodeURIComponent(id)}/results`),
  getCompanies: () => request<{ companies: Company[]; count: number }>("/companies"),
};
