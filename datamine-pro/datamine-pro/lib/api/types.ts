/**
 * Contract between this frontend and the FUTURE Python backend (FastAPI + Scrapy/Playwright/Pandas).
 * Nothing here is used for real scraping yet. When you build the backend, make it return these shapes.
 * See /backend/README.md for the endpoint list.
 */
import type { Company } from "../types";

export interface ExtractionRequest {
  projectName: string;
  sourceUrls: string[];
  country: string;
  employeeRange: { min: number | null; max: number | null };
  turnoverRange: { min: number | null; max: number | null };
  fields: string[];
  /** User confirmed they may lawfully collect from these sources. */
  complianceConfirmed: boolean;
}

export type JobState = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ExtractionJob {
  id: string;
  state: JobState;
  progress: number; // 0-100
  message?: string;
  recordsFound: number;
}

export interface JobResults {
  job: ExtractionJob;
  /** Real records must be returned with origin: "extracted". */
  companies: Company[];
}
