"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { FolderOpen, Globe, PlusCircle, Search, Trash2 } from "lucide-react";
import { useApp } from "@/context/AppContext";
import type { ProjectStatus } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge, SampleBadge } from "@/components/ui/Badge";
import { ProjectStatusBadge } from "@/components/ui/ProjectStatusBadge";
import { formatDate, prettyUrl } from "@/lib/format";

const STATUSES: ("All" | ProjectStatus)[] = ["All", "Completed", "Running", "Queued", "Failed"];

export function ProjectsView() {
  const { projects, deleteProject, showToast } = useApp();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"All" | ProjectStatus>("All");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return projects.filter(
      (p) =>
        (status === "All" || p.status === status) &&
        (!q || p.name.toLowerCase().includes(q) || p.sources.some((s) => s.toLowerCase().includes(q)))
    );
  }, [projects, query, status]);

  return (
    <>
      <PageHeader
        title="My Projects"
        description="Every extraction you configure appears here. In this version, projects are simulated demo runs."
        actions={
          <Link href="/new-extraction" className="btn-primary">
            <PlusCircle className="h-4 w-4" aria-hidden /> New Extraction
          </Link>
        }
      />

      <div className="card mb-4 flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <div className="relative sm:max-w-sm sm:flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
          <input type="search" aria-label="Search projects" className="field pl-9" placeholder="Search projects or sources…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          {STATUSES.map((s) => (
            <button key={s} onClick={() => setStatus(s)} aria-pressed={status === s} className={`chip ${status === s ? "chip-active" : ""}`}>
              {s}
            </button>
          ))}
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="card">
          <EmptyState icon={<FolderOpen className="h-6 w-6" />} title="No projects found" description="Change the search or status filter, or start a new extraction." />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((p) => (
            <article key={p.id} className="card flex flex-col p-5 transition duration-200 hover:-translate-y-0.5 hover:border-brand/50">
              <div className="mb-3 flex items-start justify-between gap-3">
                <h2 className="text-base font-semibold leading-snug">{p.name}</h2>
                <ProjectStatusBadge status={p.status} />
              </div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                {p.origin === "sample" ? <SampleBadge /> : <Badge tone="brand">Demo run · simulated</Badge>}
                <span className="text-xs text-muted">{p.country}</span>
              </div>
              <ul className="mb-4 space-y-1 text-xs text-muted">
                {p.sources.slice(0, 3).map((s) => (
                  <li key={s} className="flex items-center gap-1.5 truncate"><Globe className="h-3.5 w-3.5 shrink-0" aria-hidden />{prettyUrl(s)}</li>
                ))}
                {p.sources.length > 3 && <li>+{p.sources.length - 3} more</li>}
              </ul>
              <div className="mt-auto">
                <div className="mb-1.5 flex justify-between text-xs text-muted">
                  <span>{p.recordsFound} records</span>
                  <span>{p.progress}%</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={p.progress} aria-valuemin={0} aria-valuemax={100} aria-label={`${p.name} progress`}>
                  <div className="h-full rounded-full bg-brand" style={{ width: `${p.progress}%` }} />
                </div>
                <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-xs text-muted">
                  <span>Created {formatDate(p.createdAt)}</span>
                  {p.origin === "demo-run" && (
                    <button className="flex items-center gap-1 font-medium text-bad hover:underline" onClick={() => { deleteProject(p.id); showToast("Project deleted"); }}>
                      <Trash2 className="h-3.5 w-3.5" aria-hidden /> Delete
                    </button>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
