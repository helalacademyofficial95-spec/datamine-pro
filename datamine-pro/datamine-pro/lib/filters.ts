import type { Company, Country, SortDir, SortKey, VerificationStatus } from "./types";

export const EMPLOYEE_BANDS = [
  { id: "1-9", label: "1–9", min: 1, max: 9 },
  { id: "10-19", label: "10–19", min: 10, max: 19 },
  { id: "20-49", label: "20–49", min: 20, max: 49 },
  { id: "50-99", label: "50–99", min: 50, max: 99 },
  { id: "100-249", label: "100–249", min: 100, max: 249 },
] as const;

export const TURNOVER_BANDS = [
  { id: "below1m", label: "Below €1M" },
  { id: "above1m", label: "Above €1M" },
  { id: "above5m", label: "Above €5M" },
  { id: "above10m", label: "Above €10M" },
] as const;

export type EmployeeFilter = "all" | (typeof EMPLOYEE_BANDS)[number]["id"] | "custom";
export type TurnoverFilter = "all" | (typeof TURNOVER_BANDS)[number]["id"] | "custom";

export interface CompanyFilters {
  search: string;
  country: "all" | Country;
  employees: EmployeeFilter;
  employeesMin: string; // used when employees === "custom"
  employeesMax: string;
  turnover: TurnoverFilter;
  turnoverMin: string; // euros, used when turnover === "custom"
  turnoverMax: string;
  verification: "all" | VerificationStatus;
  b2c: "all" | "yes" | "no";
}

export const DEFAULT_FILTERS: CompanyFilters = {
  search: "",
  country: "all",
  employees: "all",
  employeesMin: "",
  employeesMax: "",
  turnover: "all",
  turnoverMin: "",
  turnoverMax: "",
  verification: "all",
  b2c: "all",
};

/** Parses "1 500 000", "1,5" etc. Returns null for empty / invalid input. */
export function parseNumber(text: string): number | null {
  const cleaned = text.replace(/[\s ]/g, "").replace(",", ".");
  if (cleaned === "") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) && n >= 0 ? n : null;
}

function matchesEmployees(c: Company, f: CompanyFilters): boolean {
  if (f.employees === "all") return true;
  if (f.employees === "custom") {
    const min = parseNumber(f.employeesMin);
    const max = parseNumber(f.employeesMax);
    return (min === null || c.employees >= min) && (max === null || c.employees <= max);
  }
  const band = EMPLOYEE_BANDS.find((b) => b.id === f.employees);
  return band ? c.employees >= band.min && c.employees <= band.max : true;
}

function matchesTurnover(c: Company, f: CompanyFilters): boolean {
  switch (f.turnover) {
    case "all":
      return true;
    case "below1m":
      return c.turnover < 1_000_000;
    case "above1m":
      return c.turnover >= 1_000_000;
    case "above5m":
      return c.turnover >= 5_000_000;
    case "above10m":
      return c.turnover >= 10_000_000;
    case "custom": {
      const min = parseNumber(f.turnoverMin);
      const max = parseNumber(f.turnoverMax);
      return (min === null || c.turnover >= min) && (max === null || c.turnover <= max);
    }
  }
}

export function filterCompanies(companies: Company[], f: CompanyFilters): Company[] {
  const q = f.search.trim().toLowerCase();
  return companies.filter((c) => {
    if (q) {
      const haystack = [c.name, c.director, c.email, c.phone, c.country, c.address, c.website, c.b2cWebsite ?? ""]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    if (f.country !== "all" && c.country !== f.country) return false;
    if (!matchesEmployees(c, f)) return false;
    if (!matchesTurnover(c, f)) return false;
    if (f.verification !== "all" && c.verification !== f.verification) return false;
    if (f.b2c === "yes" && !c.b2cWebsite) return false;
    if (f.b2c === "no" && c.b2cWebsite) return false;
    return true;
  });
}

export function sortCompanies(companies: Company[], key: SortKey, dir: SortDir): Company[] {
  const factor = dir === "asc" ? 1 : -1;
  const value = (c: Company): string | number => {
    switch (key) {
      case "b2cWebsite":
        return c.b2cWebsite ?? "";
      default:
        return c[key];
    }
  };
  return [...companies].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    if (typeof x === "number" && typeof y === "number") return (x - y) * factor;
    return String(x).localeCompare(String(y), "en", { sensitivity: "base" }) * factor;
  });
}

export function countActiveFilters(f: CompanyFilters): number {
  let n = 0;
  if (f.search.trim()) n++;
  if (f.country !== "all") n++;
  if (f.employees !== "all") n++;
  if (f.turnover !== "all") n++;
  if (f.verification !== "all") n++;
  if (f.b2c !== "all") n++;
  return n;
}
