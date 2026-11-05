import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { Company } from "@/lib/types";
import { SampleBadge } from "@/components/ui/Badge";
import { VerificationBadge } from "@/components/ui/VerificationBadge";
import { formatEuro, formatNumber, initials } from "@/lib/format";

export function RecentCompanies({ companies }: { companies: Company[] }) {
  return (
    <div className="card p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold">Recent company records</h2>
          <SampleBadge />
        </div>
        <Link href="/companies" className="flex items-center gap-1 text-sm font-medium text-brand hover:underline">
          Open full table <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
      <div className="thin-scroll -mx-5 overflow-x-auto px-5">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <th className="pb-2 font-semibold">Company</th>
              <th className="pb-2 font-semibold">Country</th>
              <th className="pb-2 text-right font-semibold">Employees</th>
              <th className="pb-2 text-right font-semibold">Turnover</th>
              <th className="pb-2 pl-6 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {companies.map((c) => (
              <tr key={c.id} className="transition hover:bg-brand/5">
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-xs font-bold text-brand">{initials(c.name)}</span>
                    <div className="min-w-0">
                      <div className="truncate font-medium">{c.name}</div>
                      <div className="truncate text-xs text-muted">{c.director}</div>
                    </div>
                  </div>
                </td>
                <td className="py-3 pr-4 text-muted">{c.country}</td>
                <td className="py-3 pr-4 text-right tabular-nums">{formatNumber(c.employees)}</td>
                <td className="py-3 text-right tabular-nums">{formatEuro(c.turnover)}</td>
                <td className="py-3 pl-6">
                  <VerificationBadge status={c.verification} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
