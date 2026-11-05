import type { Company, ExtractionJob, ExtractionRequest, JobResults } from "./types";

/**
 * API client for the Python (FastAPI) extraction backend.
 *
 * Next.js inlines NEXT_PUBLIC_* variables at BUILD time. If the variable is missing
 * from a Vercel build, the app used to silently fall back to invented sample data.
 * To prevent that, the public production API URL below is the default, and sample
 * data is only shown when NEXT_PUBLIC_DEMO_MODE=true is set explicitly.
 * (The URL is public; it is not a secret. Never put credentials in NEXT_PUBLIC_* values.)
 */
const DEFAULT_API_URL = "https://datamine-pro-api.onrender.com";

const DEMO_MODE = (process.env.NEXT_PUBLIC_DEMO_MODE ?? "").trim().toLowerCase() === "true";

function resolveBaseUrl(): string {
  if (DEMO_MODE) return "";
  const configured = (process.env.NEXT_PUBLIC_API_URL ?? "").trim();
  // The placeholder from .env.example (https://your-python-api.example) is not a real server.
  const isPlaceholder = /\.example(\/|$)/i.test(configured);
  return (configured && !isPlaceholder ? configured : DEFAULT_API_URL).replace(/\/$/, "");
}

const BASE_URL = resolveBaseUrl();

export const isDemoMode = (): boolean => DEMO_MODE;
export const isBackendConfigured = (): boolean => BASE_URL.length > 0;
export const getBackendUrl = (): string => BASE_URL;

interface RequestOptions {
  /** Abort a single attempt after this many milliseconds. */
  timeoutMs?: number;
  /** Extra attempts after a network error, timeout or 502/503/504 (e.g. Render Free waking up). */
  retries?: number;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Errors worth retrying: the server may simply still be waking up. */
class TransientError extends Error {}

async function attempt<T>(path: string, init: RequestInit | undefined, timeoutMs: number): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
    if (!response.ok) {
      const message = `Backend error ${response.status}`;
      if ([502, 503, 504].includes(response.status)) throw new TransientError(message);
      throw new Error(message);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof TransientError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new TransientError("The extraction service did not respond in time.");
    }
    // fetch() rejects with TypeError on network failure or a blocked cross-origin (CORS) request.
    if (error instanceof TypeError) {
      throw new TransientError("Could not reach the extraction service.");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function request<T>(path: string, init?: RequestInit, options: RequestOptions = {}): Promise<T> {
  if (!isBackendConfigured()) {
    throw new Error("Backend not configured. Demo mode is enabled (NEXT_PUBLIC_DEMO_MODE=true).");
  }
  const { timeoutMs = 30_000, retries = 0 } = options;
  let lastError: unknown;
  for (let i = 0; i <= retries; i++) {
    try {
      return await attempt<T>(path, init, timeoutMs);
    } catch (error) {
      lastError = error;
      if (!(error instanceof TransientError) || i === retries) break;
      await sleep(2_000 * (i + 1));
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Request failed.");
}

export const api = {
  health: () => request<{ status: "ok" }>("/health", undefined, { timeoutMs: 45_000, retries: 1 }),
  createJob: (body: ExtractionRequest) =>
    request<ExtractionJob>("/jobs", { method: "POST", body: JSON.stringify(body) }, { timeoutMs: 60_000 }),
  getJob: (id: string) => request<ExtractionJob>(`/jobs/${encodeURIComponent(id)}`),
  cancelJob: (id: string) => request<ExtractionJob>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  getResults: (id: string) => request<JobResults>(`/jobs/${encodeURIComponent(id)}/results`, undefined, { timeoutMs: 60_000 }),
  // Generous timeout and retries: the first call can take about a minute while Render Free wakes up.
  getCompanies: () =>
    request<{ companies: Company[]; count: number }>("/companies", undefined, { timeoutMs: 60_000, retries: 2 }),
};
