import { categoryOf } from "./filters";
import type { Company } from "./types";

/** Columns written to CSV / Excel files, in order. */
export interface ExportColumn {
  header: string;
  width: number;
  value: (c: Company) => string | number;
}

const BANDS: Record<string, string> = {
  "01": "1-2", "02": "3-5", "03": "6-9", "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199",
  "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999", "51": "2000-4999",
  "52": "5000-9999", "53": "10000+",
};
const STATUS_LABEL: Record<string, string> = {
  verified: "Verified", partially_verified: "Partially Verified", unverified: "Unverified",
  not_found: "Not Found", not_applicable: "Not Applicable",
};
const orNotFound = (value: string | null | undefined) => (value && value.trim() ? value : "Not Found");
const statusText = (value?: string) => (value ? STATUS_LABEL[value] ?? "Not checked" : "Not checked");

export const EXPORT_COLUMNS: ExportColumn[] = [
  { header: "Company Name", width: 34, value: (c) => c.name },
  { header: "Registration Number (SIREN)", width: 18, value: (c) => c.siren ?? "" },
  { header: "Contact Person", width: 24, value: (c) => orNotFound(c.director) },
  { header: "Email", width: 34, value: (c) => orNotFound(c.email) },
  { header: "Email Source URL", width: 38, value: (c) => c.emailSource ?? "" },
  { header: "Phone", width: 20, value: (c) => orNotFound(c.phone) },
  { header: "Phone Source URL", width: 38, value: (c) => c.phoneSource ?? "" },
  { header: "Official Website", width: 38, value: (c) => orNotFound(c.website) },
  { header: "Official Website Status", width: 20, value: (c) => statusText(c.websiteStatus) },
  { header: "Official Website Source URL", width: 40, value: (c) => c.websiteSourceUrl ?? "" },
  { header: "B2C Website", width: 38, value: (c) => orNotFound(c.b2cWebsite) },
  { header: "B2C Status", width: 20, value: (c) => statusText(c.b2cWebsiteStatus) },
  { header: "B2C Source URL", width: 40, value: (c) => c.b2cSourceUrl ?? "" },
  { header: "Website Check Date", width: 18, value: (c) => c.checkedAt ?? "" },
  { header: "Employee Band (registry)", width: 22, value: (c) => (c.employeeBand && BANDS[c.employeeBand]) || "" },
  { header: "Employees (exact)", width: 16, value: (c) => (c.employees > 0 ? c.employees : "") },
  { header: "Annual Turnover (EUR)", width: 22, value: (c) => (c.turnover > 0 ? c.turnover : "") },
  { header: "Turnover Year", width: 14, value: (c) => (c.turnoverYear ? c.turnoverYear : "") },
  { header: "Country", width: 14, value: (c) => c.country },
  { header: "Address", width: 46, value: (c) => c.address },
  { header: "Registry Source URL", width: 44, value: (c) => c.registryUrl ?? "" },
  { header: "Verification Status", width: 20, value: (c) => c.verification },
  { header: "Data Origin", width: 16, value: (c) => (c.origin === "sample" ? "SAMPLE DATA" : "Extracted") },
  { header: "Business Category", width: 40, value: (c) => categoryOf(c) },
];

const PHONE_LIKE = /^[+-]?[\d\s().-]+$/;

/** Escapes one CSV cell (RFC 4180) and neutralises spreadsheet formula injection. */
export function csvCell(value: string | number): string {
  let text = String(value);
  if (typeof value === "string" && /^[=+\-@\t\r]/.test(text) && !PHONE_LIKE.test(text)) {
    text = `'${text}`;
  }
  if (/[",\r\n]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function buildCsv(companies: Company[]): string {
  const lines = [EXPORT_COLUMNS.map((c) => csvCell(c.header)).join(",")];
  for (const company of companies) {
    lines.push(EXPORT_COLUMNS.map((c) => csvCell(c.value(company))).join(","));
  }
  return lines.join("\r\n");
}
