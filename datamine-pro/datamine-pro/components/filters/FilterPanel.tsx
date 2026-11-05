"use client";

import { Search } from "lucide-react";
import { CompanyFilters, EMPLOYEE_BANDS, TURNOVER_BANDS } from "@/lib/filters";

interface Props {
  filters: CompanyFilters;
  onChange: (next: CompanyFilters) => void;
  /** Hide the search box when the page already has its own */
  showSearch?: boolean;
}

/** The same filter form is used on the Extracted Companies page and the Data Filters page. */
export function FilterPanel({ filters, onChange, showSearch = true }: Props) {
  const set = <K extends keyof CompanyFilters>(key: K, value: CompanyFilters[K]) => onChange({ ...filters, [key]: value });

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {showSearch && (
        <div className="sm:col-span-2 lg:col-span-3">
          <label htmlFor="f-search" className="label">Search</label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
            <input
              id="f-search"
              type="search"
              className="field pl-9"
              placeholder="Company, director, e-mail, phone, address…"
              value={filters.search}
              onChange={(e) => set("search", e.target.value)}
            />
          </div>
        </div>
      )}

      <div>
        <label htmlFor="f-country" className="label">Country</label>
        <select id="f-country" className="field" value={filters.country} onChange={(e) => set("country", e.target.value as CompanyFilters["country"])}>
          <option value="all">All countries</option>
          <option value="France">France</option>
          <option value="Belgium">Belgium</option>
          <option value="Luxembourg">Luxembourg</option>
        </select>
      </div>

      <div>
        <label htmlFor="f-emp" className="label">Employees</label>
        <select id="f-emp" className="field" value={filters.employees} onChange={(e) => set("employees", e.target.value as CompanyFilters["employees"])}>
          <option value="all">Any size</option>
          {EMPLOYEE_BANDS.map((b) => (
            <option key={b.id} value={b.id}>{b.label}</option>
          ))}
          <option value="custom">Custom range…</option>
        </select>
        {filters.employees === "custom" && (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <input aria-label="Minimum employees" inputMode="numeric" className="field" placeholder="Min" value={filters.employeesMin} onChange={(e) => set("employeesMin", e.target.value)} />
            <input aria-label="Maximum employees" inputMode="numeric" className="field" placeholder="Max" value={filters.employeesMax} onChange={(e) => set("employeesMax", e.target.value)} />
          </div>
        )}
      </div>

      <div>
        <label htmlFor="f-turn" className="label">Annual turnover</label>
        <select id="f-turn" className="field" value={filters.turnover} onChange={(e) => set("turnover", e.target.value as CompanyFilters["turnover"])}>
          <option value="all">Any turnover</option>
          {TURNOVER_BANDS.map((b) => (
            <option key={b.id} value={b.id}>{b.label}</option>
          ))}
          <option value="custom">Custom range…</option>
        </select>
        {filters.turnover === "custom" && (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <input aria-label="Minimum turnover in euros" inputMode="numeric" className="field" placeholder="Min €" value={filters.turnoverMin} onChange={(e) => set("turnoverMin", e.target.value)} />
            <input aria-label="Maximum turnover in euros" inputMode="numeric" className="field" placeholder="Max €" value={filters.turnoverMax} onChange={(e) => set("turnoverMax", e.target.value)} />
          </div>
        )}
      </div>

      <div>
        <label htmlFor="f-ver" className="label">Verification status</label>
        <select id="f-ver" className="field" value={filters.verification} onChange={(e) => set("verification", e.target.value as CompanyFilters["verification"])}>
          <option value="all">Any status</option>
          <option value="Verified">Verified</option>
          <option value="Partially verified">Partially verified</option>
          <option value="Unverified">Unverified</option>
        </select>
      </div>

      <div>
        <label htmlFor="f-b2c" className="label">B2C website</label>
        <select id="f-b2c" className="field" value={filters.b2c} onChange={(e) => set("b2c", e.target.value as CompanyFilters["b2c"])}>
          <option value="all">Any</option>
          <option value="yes">Has B2C website</option>
          <option value="no">No B2C website</option>
        </select>
      </div>
    </div>
  );
}
