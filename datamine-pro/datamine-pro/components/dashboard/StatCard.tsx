import type { LucideIcon } from "lucide-react";

export function StatCard({ label, value, hint, icon: Icon }: { label: string; value: string; hint: string; icon: LucideIcon }) {
  return (
    <div className="card group p-5 transition duration-200 hover:-translate-y-0.5 hover:border-brand/50">
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm font-medium text-muted">{label}</span>
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10 text-brand transition group-hover:bg-brand group-hover:text-white">
          <Icon className="h-[18px] w-[18px]" aria-hidden />
        </span>
      </div>
      <div className="text-3xl font-bold tracking-tight">{value}</div>
      <p className="mt-1 text-xs text-muted">{hint}</p>
    </div>
  );
}
