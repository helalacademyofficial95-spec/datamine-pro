"use client";

import Link from "next/link";
import { AlertTriangle, Inbox, Loader2, RefreshCw } from "lucide-react";
import { useApp } from "@/context/AppContext";

/**
 * Tells the truth about where the records on screen come from:
 * still loading, backend unreachable, or genuinely no records yet.
 * It never says "sample" — the demo notice is a separate component.
 */
export function DataStatusBanner() {
  const { dataStatus, dataError, companies, reloadCompanies } = useApp();

  if (dataStatus === "loading") {
    return (
      <div role="status" className="mb-6 flex items-start gap-3 rounded-xl border border-line bg-raised px-4 py-3 text-sm">
        <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand" aria-hidden />
        <p className="text-ink/90">
          <strong>Loading records from the extraction service…</strong>{" "}
          The free server sleeps when idle, so the first load can take up to a minute.
          {companies.length > 0 && " Showing records saved in this browser until it responds."}
        </p>
      </div>
    );
  }

  if (dataStatus === "error") {
    return (
      <div role="alert" className="mb-6 flex flex-wrap items-start gap-3 rounded-xl border border-warn/50 bg-warn/10 px-4 py-3 text-sm">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
        <p className="min-w-0 flex-1 text-ink/90">
          <strong className="text-warn">Could not load records from the extraction service.</strong>{" "}
          {dataError ? `${dataError} ` : ""}
          {companies.length > 0
            ? `Showing ${companies.length} record${companies.length === 1 ? "" : "s"} saved in this browser; they may be out of date.`
            : "No records can be shown until the service responds."}
        </p>
        <button className="btn-secondary" onClick={() => void reloadCompanies()}>
          <RefreshCw className="h-4 w-4" aria-hidden /> Retry
        </button>
      </div>
    );
  }

  if (dataStatus === "ready" && companies.length === 0) {
    return (
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-line bg-raised px-4 py-3 text-sm">
        <Inbox className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden />
        <p className="text-ink/90">
          <strong>No extracted records yet.</strong> The service is reachable but has no completed extractions.{" "}
          <Link href="/new-extraction" className="text-brand hover:underline">Start a new extraction</Link>.
        </p>
      </div>
    );
  }

  return null;
}
