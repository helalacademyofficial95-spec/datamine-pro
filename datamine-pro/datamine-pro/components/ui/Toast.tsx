"use client";

import { CheckCircle2 } from "lucide-react";
import { useApp } from "@/context/AppContext";

export function Toast() {
  const { toast } = useApp();
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex justify-center px-4">
      {toast && (
        <div className="pointer-events-auto flex animate-fade-up items-center gap-2 rounded-xl border border-line bg-surface px-4 py-3 text-sm font-medium shadow-card">
          <CheckCircle2 className="h-4 w-4 text-ok" aria-hidden />
          {toast}
        </div>
      )}
    </div>
  );
}
