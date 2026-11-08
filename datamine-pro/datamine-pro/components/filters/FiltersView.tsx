"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { BookmarkPlus, RotateCcw, Table2, Trash2 } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { categoryOptions, countActiveFilters, filterCompanies } from "@/lib/filters";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { FilterPanel } from "./FilterPanel";

export function FiltersView() {
  const { companies, filters, setFilters, resetFilters, presets, savePreset, deletePreset, showToast } = useApp();
  const [name, setName] = useState("");

  const categories = useMemo(() => categoryOptions(companies), [companies]);
  const matches = useMemo(() => filterCompanies(companies, filters).length, [companies, filters]);
  const active = countActiveFilters(filters);

  function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    savePreset(name);
    setName("");
    showToast("Filter preset saved");
  }

  return (
    <>
      <PageHeader
        title="Data Filters"
        description="Build a filter once, see how many records match, and save it as a preset. The same filters apply on the Extracted Companies page."
        actions={
          <Link href="/companies" className="btn-primary">
            <Table2 className="h-4 w-4" aria-hidden /> View {matches} result{matches === 1 ? "" : "s"}
          </Link>
        }
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className="card p-5 xl:col-span-2" aria-label="Filter builder">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-base font-semibold">Filter builder</h2>
            <button className="btn-ghost !py-1.5" onClick={resetFilters} disabled={active === 0}>
              <RotateCcw className="h-4 w-4" aria-hidden /> Reset all
            </button>
          </div>
          <FilterPanel filters={filters} onChange={setFilters} categories={categories} />
          <div className="mt-6 flex items-center justify-between rounded-xl bg-brand/10 px-4 py-3 text-sm">
            <span className="text-muted">{active} active filter{active === 1 ? "" : "s"}</span>
            <span><strong className="text-lg">{matches}</strong> <span className="text-muted">of {companies.length} sample records match</span></span>
          </div>
        </section>

        <section className="card p-5" aria-label="Saved presets">
          <h2 className="mb-1 text-base font-semibold">Saved presets</h2>
          <p className="mb-4 text-xs text-muted">Stored only in this browser.</p>
          <form onSubmit={onSave} className="mb-4 flex gap-2">
            <input className="field" placeholder="Preset name" aria-label="Preset name" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} />
            <button className="btn-primary shrink-0 !px-3" type="submit" disabled={!name.trim()} aria-label="Save preset">
              <BookmarkPlus className="h-4 w-4" />
            </button>
          </form>
          {presets.length === 0 ? (
            <EmptyState icon={<BookmarkPlus className="h-5 w-5" />} title="No presets yet" description="Set some filters, name them and press save." />
          ) : (
            <ul className="space-y-2">
              {presets.map((p) => (
                <li key={p.id} className="flex items-center gap-2 rounded-xl border border-line bg-raised p-2 pl-3">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{p.name}</span>
                  <button className="btn-secondary !px-3 !py-1.5 text-xs" onClick={() => { setFilters(p.filters); showToast(`Applied “${p.name}”`); }}>
                    Apply
                  </button>
                  <button className="btn-ghost !px-2 !py-1.5" onClick={() => deletePreset(p.id)} aria-label={`Delete preset ${p.name}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
