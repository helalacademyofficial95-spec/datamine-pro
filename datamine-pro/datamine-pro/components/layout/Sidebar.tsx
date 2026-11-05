"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Database, X } from "lucide-react";
import { NAV_ITEMS } from "@/lib/nav";
import { useApp } from "@/context/AppContext";

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const { dataStatus, companies } = useApp();

  const sourceStatus =
    dataStatus === "loading"
      ? "Connecting to extraction backend…"
      : dataStatus === "ready"
        ? `Live backend connected · ${companies.length} records loaded.`
        : dataStatus === "error"
          ? companies.length > 0
            ? `Backend unavailable · showing ${companies.length} saved browser records.`
            : "Backend unavailable · no records loaded."
          : "Demo mode · showing sample records.";

  return (
    <>
      {/* Dark overlay behind the drawer on phones / tablets */}
      <div
        className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
        aria-hidden
      />
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col bg-sidebar text-slate-300 transition-transform duration-300 lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
        aria-label="Main navigation"
      >
        <div className="flex h-16 items-center justify-between border-b border-white/10 px-5">
          <Link href="/" className="flex items-center gap-2.5" onClick={onClose}>
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 text-white shadow-lg shadow-blue-500/30">
              <Database className="h-5 w-5" aria-hidden />
            </span>
            <span className="text-lg font-bold tracking-tight text-white">
              DataMine <span className="text-cyan-300">Pro</span>
            </span>
          </Link>
          <button className="rounded-lg p-2 text-slate-400 hover:bg-white/10 hover:text-white lg:hidden" onClick={onClose} aria-label="Close menu">
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-5">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                onClick={onClose}
                aria-current={active ? "page" : undefined}
                className={`group flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition ${
                  active ? "bg-blue-500/15 text-white ring-1 ring-inset ring-blue-400/30" : "hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon className={`h-[18px] w-[18px] transition ${active ? "text-cyan-300" : "text-slate-400 group-hover:text-cyan-300"}`} aria-hidden />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="m-3 rounded-xl border border-white/10 bg-white/5 p-4 text-xs leading-relaxed text-slate-400" aria-live="polite">
          <p className="mb-1 font-semibold text-slate-200">Data source status</p>
          {sourceStatus}
        </div>
      </aside>
    </>
  );
}
