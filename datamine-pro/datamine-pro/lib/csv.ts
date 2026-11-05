import type { Company } from "./types";

/** Columns written to CSV / Excel files, in order. */
export interface ExportColumn {
  header: string;
  width: number;
  value: (c: Company) => string | number;
}

export const EXPORT_COLUMNS: ExportColumn[] = [
  { header: "Company Name", width: 34, value: (c) => c.name },
  { header: "Director", width: 22, value: (c) => c.director },
  { header: "Email", width: 36, value: (c) => c.email },
  { header: "Phone", width: 20, value: (c) => c.phone },
  { header: "Employees", width: 12, value: (c) => c.employees },
  { header: "Annual Turnover (EUR)", width: 22, value: (c) => c.turnover },
  { header: "Country", width: 14, value: (c) => c.country },
  { header: "Address", width: 46, value: (c) => c.address },
  { header: "Company Website", width: 38, value: (c) => c.website },
  { header: "B2C Website", width: 38, value: (c) => c.b2cWebsite ?? "" },
  { header: "Verification Status", width: 20, value: (c) => c.verification },
  { header: "Data Origin", width: 16, value: (c) => (c.origin === "sample" ? "SAMPLE DATA" : "Extracted") },
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
