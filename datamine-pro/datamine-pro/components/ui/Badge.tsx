import type { ReactNode } from "react";

export type BadgeTone = "ok" | "warn" | "bad" | "brand" | "neutral";

const TONES: Record<BadgeTone, string> = {
  ok: "bg-ok/15 text-ok",
  warn: "bg-warn/15 text-warn",
  bad: "bg-bad/15 text-bad",
  brand: "bg-brand/15 text-brand",
  neutral: "bg-muted/15 text-muted",
};

export function Badge({ tone = "neutral", children, dot = false }: { tone?: BadgeTone; children: ReactNode; dot?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone]}`}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}

/** Shown wherever data is NOT real extracted data. */
export function SampleBadge({ label = "Sample data" }: { label?: string }) {
  return (
    <span className="inline-flex items-center rounded-md border border-dashed border-warn/60 bg-warn/10 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-warn">
      {label}
    </span>
  );
}
