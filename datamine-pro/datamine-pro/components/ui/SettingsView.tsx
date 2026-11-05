"use client";

import { useState } from "react";
import { Moon, PlugZap, RotateCcw, Scale, Sun } from "lucide-react";
import { PageHeader } from "./PageHeader";
import { Badge } from "./Badge";
import { useTheme } from "@/context/ThemeContext";
import { useApp } from "@/context/AppContext";
import { getBackendUrl, isBackendConfigured } from "@/lib/api/client";

export function SettingsView() {
  const { theme, setTheme } = useTheme();
  const { resetDemoData, showToast } = useApp();
  const [confirmReset, setConfirmReset] = useState(false);
  const connected = isBackendConfigured();

  return (
    <>
      <PageHeader title="Settings" description="Appearance, backend connection and responsible-use rules." />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="card p-5">
          <h2 className="mb-1 text-base font-semibold">Appearance</h2>
          <p className="mb-4 text-sm text-muted">Choose the colour theme. Your choice is remembered in this browser.</p>
          <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-label="Theme">
            {([
              ["dark", "Dark navy", Moon],
              ["light", "Light", Sun],
            ] as const).map(([id, label, Icon]) => (
              <button
                key={id}
                role="radio"
                aria-checked={theme === id}
                onClick={() => setTheme(id)}
                className={`flex items-center justify-center gap-2 rounded-xl border px-4 py-4 text-sm font-semibold transition ${theme === id ? "border-brand bg-brand/10" : "border-line bg-raised hover:border-brand/50"}`}
              >
                <Icon className="h-4 w-4" aria-hidden /> {label}
              </button>
            ))}
          </div>
        </section>

        <section className="card p-5">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-base font-semibold">Backend connection</h2>
            <Badge tone={connected ? "ok" : "warn"} dot>{connected ? "Address set" : "Not connected"}</Badge>
          </div>
          <p className="mb-3 text-sm text-muted">
            The Python backend (Scrapy, BeautifulSoup, Playwright, Pandas, OpenPyXL) is not built yet. The app runs fully on sample data.
          </p>
          <div className="rounded-xl border border-line bg-raised p-3 text-xs">
            <div className="mb-1 flex items-center gap-1.5 font-semibold"><PlugZap className="h-3.5 w-3.5" aria-hidden /> NEXT_PUBLIC_API_URL</div>
            <code className="break-all text-muted">{connected ? getBackendUrl() : "(empty — demo mode)"}</code>
          </div>
          <p className="mt-3 text-xs text-muted">Later: copy <code>.env.example</code> to <code>.env.local</code> and set the address of your backend. See <code>backend/README.md</code>.</p>
        </section>

        <section className="card p-5 lg:col-span-2">
          <h2 className="mb-3 flex items-center gap-2 text-base font-semibold"><Scale className="h-4 w-4 text-brand" aria-hidden /> Responsible data collection</h2>
          <ul className="grid gap-2 text-sm text-muted sm:grid-cols-2">
            {[
              "Collect only publicly available business information.",
              "Respect each website's terms of use and robots.txt.",
              "Apply rate limits so you never overload a site.",
              "Never bypass CAPTCHAs, logins or other access restrictions.",
              "Follow privacy laws such as the GDPR when handling names and contact details of people.",
              "Keep only the data you need and delete it when you no longer need it.",
            ].map((t) => (
              <li key={t} className="flex gap-2"><span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-hidden />{t}</li>
            ))}
          </ul>
        </section>

        <section className="card p-5 lg:col-span-2">
          <h2 className="mb-1 text-base font-semibold">Reset demo data</h2>
          <p className="mb-4 text-sm text-muted">Removes demo projects, export history and saved filter presets stored in this browser. Sample companies are not affected.</p>
          {!confirmReset ? (
            <button className="btn-secondary" onClick={() => setConfirmReset(true)}><RotateCcw className="h-4 w-4" aria-hidden /> Reset demo data…</button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm">Are you sure?</span>
              <button className="btn-primary !bg-bad" onClick={() => { resetDemoData(); setConfirmReset(false); showToast("Demo data reset"); }}>Yes, reset</button>
              <button className="btn-ghost" onClick={() => setConfirmReset(false)}>Cancel</button>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
