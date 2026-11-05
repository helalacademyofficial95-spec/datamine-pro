"use client";

import Link from "next/link";
import { Download, FileSpreadsheet, FileText, Trash2 } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Badge } from "@/components/ui/Badge";
import { formatDateTime, formatNumber } from "@/lib/format";

export function ExportHistoryView() {
  const { exportLog, clearExportLog, showToast } = useApp();

  return (
    <>
      <PageHeader
        title="Export History"
        description="A log of the CSV and Excel files you downloaded from this browser. Files themselves are saved on your computer, not on a server."
        actions={
          exportLog.length > 0 ? (
            <button className="btn-secondary" onClick={() => { clearExportLog(); showToast("Export history cleared"); }}>
              <Trash2 className="h-4 w-4" aria-hidden /> Clear history
            </button>
          ) : undefined
        }
      />

      <div className="card overflow-hidden">
        {exportLog.length === 0 ? (
          <EmptyState
            icon={<Download className="h-6 w-6" />}
            title="No exports yet"
            description="Download a CSV or Excel file from the Extracted Companies page and it will be listed here."
            action={<Link href="/companies" className="btn-primary">Go to Extracted Companies</Link>}
          />
        ) : (
          <div className="thin-scroll overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-raised text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 font-semibold">File</th>
                  <th className="px-4 py-3 font-semibold">Format</th>
                  <th className="px-4 py-3 font-semibold">Scope</th>
                  <th className="px-4 py-3 text-right font-semibold">Records</th>
                  <th className="px-4 py-3 font-semibold">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {exportLog.map((e) => (
                  <tr key={e.id} className="transition hover:bg-brand/5">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 font-medium">
                        {e.format === "CSV" ? <FileText className="h-4 w-4 text-brand" aria-hidden /> : <FileSpreadsheet className="h-4 w-4 text-ok" aria-hidden />}
                        {e.filename}
                      </div>
                    </td>
                    <td className="px-4 py-3"><Badge tone={e.format === "CSV" ? "brand" : "ok"}>{e.format === "CSV" ? "CSV" : "Excel (.xlsx)"}</Badge></td>
                    <td className="px-4 py-3 text-muted">{e.scope === "selected" ? "Selected records" : "All filtered records"}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatNumber(e.count)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted">{formatDateTime(e.createdAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
