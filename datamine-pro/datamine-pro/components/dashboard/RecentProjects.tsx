import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Project } from "@/lib/types";
import { Badge, SampleBadge } from "@/components/ui/Badge";
import { ProjectStatusBadge } from "@/components/ui/ProjectStatusBadge";
import { formatDate } from "@/lib/format";

export function RecentProjects({ projects }: { projects: Project[] }) {
  return (
    <div className="card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold">Recent extraction projects</h2>
        <Link href="/projects" className="flex items-center gap-1 text-sm font-medium text-brand hover:underline">
          View all <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
      <ul className="divide-y divide-line">
        {projects.map((p) => (
          <li key={p.id} className="flex items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-semibold">{p.name}</span>
                {p.origin === "sample" ? <SampleBadge /> : <Badge tone="brand">Demo run</Badge>}
              </div>
              <div className="mt-1 text-xs text-muted">
                {p.country} · {p.recordsFound} records · {formatDate(p.createdAt)}
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={p.progress} aria-valuemin={0} aria-valuemax={100} aria-label={`${p.name} progress`}>
                <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${p.progress}%` }} />
              </div>
            </div>
            <ProjectStatusBadge status={p.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
