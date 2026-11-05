export type Country = "France" | "Belgium" | "Luxembourg" | "Other";
export type VerificationStatus = "Verified" | "Partially verified" | "Unverified";

/** "sample" = built-in demonstration record. "extracted" = real data from the future Python backend. */
export type DataOrigin = "sample" | "extracted";

export interface Company {
  id: string;
  name: string;
  director: string;
  email: string;
  phone: string;
  employees: number;
  /** Annual turnover in euros */
  turnover: number;
  country: Country;
  address: string;
  website: string;
  /** null when no B2C website was matched */
  b2cWebsite: string | null;
  emailVerified: boolean;
  phoneVerified: boolean;
  verification: VerificationStatus;
  origin: DataOrigin;
  /** ISO date (YYYY-MM-DD) */
  extractedAt: string;
}

export type ProjectStatus = "Completed" | "Running" | "Queued" | "Failed";

export interface Project {
  id: string;
  name: string;
  sources: string[];
  country: string;
  status: ProjectStatus;
  progress: number; // 0-100
  recordsFound: number;
  createdAt: string; // ISO date
  origin: "sample" | "demo-run";
}

export type ExportFormat = "CSV" | "Excel";
export type ExportScope = "selected" | "filtered";

export interface ExportLogEntry {
  id: string;
  createdAt: string; // ISO timestamp
  format: ExportFormat;
  scope: ExportScope;
  count: number;
  filename: string;
}

export type SortKey =
  | "name"
  | "director"
  | "email"
  | "phone"
  | "employees"
  | "turnover"
  | "country"
  | "b2cWebsite"
  | "verification";
export type SortDir = "asc" | "desc";
