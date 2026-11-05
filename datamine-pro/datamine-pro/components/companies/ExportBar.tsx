"use client";

import { useState } from "react";
import { FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import type { Company, ExportFormat, ExportScope } from "@/lib/types";
import { buildFilename, downloadCsv, downloadXlsx } from "@/lib/export";
import { useApp } from "@/context/AppContext";

interface Props {
  selected: Company[]; // records ticked in the table
  filtered: Company[]; // every record matching the current filters
}

export function ExportBar({ selected, filtered }: Props) {
  const { addExportLog, showToast } = useApp();
  const [scope, setScope] = useState<ExportScope>("selected");
  const [busy, setBusy] = useState<ExportFormat | null>(null);

  // With nothing ticked there is nothing to export as "selected"
  const effectiveScope: ExportScope = selected.length > 0 ? scope : "filtered";
  const rows = effectiveScope === "selected" ? selected : filtered;

  async function run(format: ExportFormat) {
    if (rows.length === 0 || busy) return;
    setBusy(format);
    try {
      const filename = buildFilename(format === "CSV" ? "csv" : "xlsx");
      if (format === "CSV") downloadCsv(rows, filename);
      else await downloadXlsx(rows, filename);
      addExportLog({
        id: `exp-${Date.now()}`,
        createdAt: new Date().toISOString(),
        format,
        scope: effectiveScope,
        count: rows.length,
        filename,
      });
      showToast(`${format} downloaded: ${rows.length} record${rows.length === 1 ? "" : "s"}`);
    } catch (err) {
      console.error(err);
      showToast("Export failed. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="inline-flex rounded-xl border border-line bg-raised p-1 text-sm" role="group" aria-label="Export scope">
        <button
          type="button"
          onClick={() => setScope("selected")}
          disabled={selected.length === 0}
          aria-pressed={effectiveScope === "selected"}
          className={`rounded-lg px-3 py-1.5 font-medium transition disabled:opacity-40 ${effectiveScope === "selected" ? "bg-brand text-white" : "text-muted hover:text-ink"}`}
        >
          Selected ({selected.length})
        </button>
        <button
          type="button"
          onClick={() => setScope("filtered")}
          aria-pressed={effectiveScope === "filtered"}
          className={`rounded-lg px-3 py-1.5 font-medium transition ${effectiveScope === "filtered" ? "bg-brand text-white" : "text-muted hover:text-ink"}`}
        >
          All filtered ({filtered.length})
        </button>
      </div>
      <button className="btn-secondary" onClick={() => run("CSV")} disabled={rows.length === 0 || busy !== null}>
        {busy === "CSV" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" aria-hidden />} Download CSV
      </button>
      <button className="btn-primary" onClick={() => run("Excel")} disabled={rows.length === 0 || busy !== null}>
        {busy === "Excel" ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSpreadsheet className="h-4 w-4" aria-hidden />} Download Excel
      </button>
    </div>
  );
}
