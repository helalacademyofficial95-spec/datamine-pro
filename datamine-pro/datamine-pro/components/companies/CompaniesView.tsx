"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, RotateCcw, Search, SearchX, SlidersHorizontal } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { countActiveFilters, filterCompanies, sortCompanies } from "@/lib/filters";
import type { SortDir, SortKey } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { EmptyState } from "@/components/ui/EmptyState";
import { SampleBadge } from "@/components/ui/Badge";
import { VerificationBadge } from "@/components/ui/VerificationBadge";
import { FilterPanel } from "@/components/filters/FilterPanel";
import { Pagination } from "./Pagination";
import { ExportBar } from "./ExportBar";
import { formatEuro, formatNumber, prettyUrl } from "@/lib/format";

const COLUMNS: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "name", label: "Company Name" },
  { key: "director", label: "Director" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "employees", label: "Employees", align: "right" },
  { key: "turnover", label: "Annual Turnover", align: "right" },
  { key: "country", label: "Country" },
  { key: "b2cWebsite", label: "B2C Website" },
  { key: "verification", label: "Verification Status" },
];

export function CompaniesView() {
  const { companies, filters, setFilters, resetFilters } = useApp();
  const [showFilters, setShowFilters] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const filtered = useMemo(
    () => sortCompanies(filterCompanies(companies, filters), sortKey, sortDir),
    [companies, filters, sortKey, sortDir]
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount);
  const pageRows = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  // Go back to page 1 whenever the filters or page size change
  useEffect(() => setPage(1), [filters, pageSize]);

  const selected = useMemo(() => companies.filter((c) => selectedIds.has(c.id)), [companies, selectedIds]);
  const selectedFiltered = useMemo(() => filtered.filter((c) => selectedIds.has(c.id)), [filtered, selectedIds]);
  const pageAllSelected = pageRows.length > 0 && pageRows.every((c) => selectedIds.has(c.id));
  const pageSomeSelected = pageRows.some((c) => selectedIds.has(c.id));
  const activeFilters = countActiveFilters(filters);

  function toggleSort(key: SortKey) {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function toggleRow(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function togglePage() {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (pageAllSelected) pageRows.forEach((c) => next.delete(c.id));
      else pageRows.forEach((c) => next.add(c.id));
      return next;
    });
  }

  const selectAllFiltered = () => setSelectedIds(new Set(filtered.map((c) => c.id)));
  const clearSelection = () => setSelectedIds(new Set());

  return (
    <>
      <PageHeader title="Extracted Companies" description="Search, filter, sort and export company records." />
      <DemoNotice />

      <div className="card mb-4 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative sm:max-w-md sm:flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
              <input
                type="search"
                aria-label="Search companies"
                className="field pl-9"
                placeholder="Search companies, directors, e-mails…"
                value={filters.search}
                onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
              />
            </div>
            <button className="btn-secondary" onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters}>
              <SlidersHorizontal className="h-4 w-4" aria-hidden />
              Filters
              {activeFilters > 0 && <span className="rounded-full bg-brand px-1.5 text-xs text-white">{activeFilters}</span>}
            </button>
            {activeFilters > 0 && (
              <button className="btn-ghost" onClick={resetFilters}>
                <RotateCcw className="h-4 w-4" aria-hidden /> Reset
              </button>
            )}
          </div>
          <ExportBar selected={selected} filtered={filtered} />
        </div>

        {showFilters && (
          <div className="mt-4 border-t border-line pt-4">
            <FilterPanel filters={filters} onChange={setFilters} showSearch={false} />
            <p className="mt-3 text-xs text-muted">
              Want to keep a set of filters? Save it on the <Link href="/filters" className="text-brand hover:underline">Data Filters</Link> page.
            </p>
          </div>
        )}
      </div>

      <div className="card overflow-hidden">
        {selectedIds.size > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line bg-brand/10 px-4 py-2.5 text-sm">
            <span><strong>{selectedIds.size}</strong> selected{selectedFiltered.length !== selectedIds.size && ` (${selectedFiltered.length} match current filters)`}</span>
            {selectedIds.size < filtered.length && (
              <button className="font-medium text-brand hover:underline" onClick={selectAllFiltered}>
                Select all {filtered.length} filtered records
              </button>
            )}
            <button className="font-medium text-brand hover:underline" onClick={clearSelection}>Clear selection</button>
          </div>
        )}

        <div className="thin-scroll overflow-x-auto">
          <table className="w-full min-w-[1180px] text-left text-sm">
            <thead className="bg-raised text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="w-12 px-4 py-3">
                  <input
                    type="checkbox"
                    className="h-4 w-4 cursor-pointer"
                    checked={pageAllSelected}
                    ref={(el) => {
                      if (el) el.indeterminate = !pageAllSelected && pageSomeSelected;
                    }}
                    onChange={togglePage}
                    aria-label="Select all records on this page"
                  />
                </th>
                {COLUMNS.map((col) => {
                  const active = col.key === sortKey;
                  const Icon = !active ? ArrowUpDown : sortDir === "asc" ? ArrowUp : ArrowDown;
                  return (
                    <th key={col.key} className={`px-3 py-3 font-semibold ${col.align === "right" ? "text-right" : ""}`} aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}>
                      <button
                        onClick={() => toggleSort(col.key)}
                        className={`inline-flex items-center gap-1.5 uppercase tracking-wide transition hover:text-ink ${active ? "text-ink" : ""}`}
                      >
                        {col.label}
                        <Icon className={`h-3.5 w-3.5 ${active ? "text-brand" : "opacity-50"}`} aria-hidden />
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {pageRows.map((c) => {
                const checked = selectedIds.has(c.id);
                return (
                  <tr key={c.id} className={`transition ${checked ? "bg-brand/10" : "hover:bg-brand/5"}`}>
                    <td className="px-4 py-3">
                      <input type="checkbox" className="h-4 w-4 cursor-pointer" checked={checked} onChange={() => toggleRow(c.id)} aria-label={`Select ${c.name}`} />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{c.name}</span>
                        {c.origin === "sample" && <SampleBadge label="Sample" />}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">{c.director}</td>
                    <td className="px-3 py-3 text-muted">{c.email}</td>
                    <td className="whitespace-nowrap px-3 py-3 tabular-nums text-muted">{c.phone}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{formatNumber(c.employees)}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{formatEuro(c.turnover)}</td>
                    <td className="px-3 py-3">{c.country}</td>
                    <td className="px-3 py-3">
                      {c.b2cWebsite ? (
                        <span className="text-brand">{prettyUrl(c.b2cWebsite)}</span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3"><VerificationBadge status={c.verification} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {filtered.length === 0 && (
          <EmptyState
            icon={<SearchX className="h-6 w-6" />}
            title="No companies match these filters"
            description="Try a broader search or clear some filters."
            action={<button className="btn-secondary" onClick={resetFilters}><RotateCcw className="h-4 w-4" /> Reset filters</button>}
          />
        )}

        <Pagination page={safePage} pageSize={pageSize} total={filtered.length} onPage={setPage} onPageSize={setPageSize} />
      </div>
    </>
  );
}
