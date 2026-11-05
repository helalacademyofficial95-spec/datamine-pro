"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Circle, Loader2, Play, Plus, ShieldCheck, X } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import {
  COUNTRY_OPTIONS, CountryOption, EMPLOYEE_OPTIONS, FIELD_OPTIONS, MAX_SOURCES, SIMULATION_STEPS, TURNOVER_OPTIONS, validateUrl,
} from "@/lib/extraction";
import { parseNumber } from "@/lib/filters";
import { api, isBackendConfigured } from "@/lib/api/client";
import { prettyUrl } from "@/lib/format";

type RunState = "idle" | "running" | "done" | "failed" | "cancelled";

export function NewExtractionView() {
  const { addProject, addCompanies, showToast } = useApp();

  const [projectName, setProjectName] = useState("");
  const [urlInput, setUrlInput] = useState("");
  const [urlError, setUrlError] = useState<string | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const [country, setCountry] = useState<CountryOption>("France");
  const [employees, setEmployees] = useState<string>("20-49");
  const [empMin, setEmpMin] = useState("");
  const [empMax, setEmpMax] = useState("");
  const [turnover, setTurnover] = useState<string>("above1m");
  const [turnMin, setTurnMin] = useState("");
  const [turnMax, setTurnMax] = useState("");
  const [fields, setFields] = useState<string[]>([...FIELD_OPTIONS]);
  const [confirmed, setConfirmed] = useState(false);

  const [runState, setRunState] = useState<RunState>("idle");
  const [stepIndex, setStepIndex] = useState(0);
  const [progressValue, setProgressValue] = useState(0);
  const [jobMessage, setJobMessage] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const finishedName = useRef("");

  function addUrl() {
    const result = validateUrl(urlInput);
    if (!result.ok) return setUrlError(result.error);
    if (sources.includes(result.url)) return setUrlError("This website is already in the list.");
    if (sources.length >= MAX_SOURCES) return setUrlError(`You can add up to ${MAX_SOURCES} source websites.`);
    setSources((s) => [...s, result.url]);
    setUrlInput("");
    setUrlError(null);
  }

  const toggleField = (f: string) => setFields((cur) => (cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]));

  const empRangeError =
    employees === "custom" && parseNumber(empMin) !== null && parseNumber(empMax) !== null && (parseNumber(empMin) as number) > (parseNumber(empMax) as number)
      ? "Minimum must not exceed maximum."
      : null;
  const turnRangeError =
    turnover === "custom" && parseNumber(turnMin) !== null && parseNumber(turnMax) !== null && (parseNumber(turnMin) as number) > (parseNumber(turnMax) as number)
      ? "Minimum must not exceed maximum."
      : null;

  const problems: string[] = [];
  if (sources.length === 0) problems.push("Add at least one source website");
  if (fields.length === 0) problems.push("Select at least one data field");
  if (empRangeError || turnRangeError) problems.push("Fix the custom range");
  if (!confirmed) problems.push("Confirm the compliance statement");
  const canStart = problems.length === 0 && runState === "idle" && isBackendConfigured();

  async function startExtraction() {
    if (!canStart) return;
    finishedName.current = projectName.trim() || `Extraction ${prettyUrl(sources[0])}`;
    setRunState("running");
    setProgressValue(0);
    setStepIndex(0);
    setRunError(null);
    setJobMessage("Submitting extraction job...");

    const employeeOption = EMPLOYEE_OPTIONS.find((option) => option.id === employees);
    const turnoverOption = TURNOVER_OPTIONS.find((option) => option.id === turnover);
    const employeeRange = employees === "custom"
      ? { min: parseNumber(empMin), max: parseNumber(empMax) }
      : { min: employeeOption?.min ?? null, max: employeeOption?.max ?? null };
    const turnoverRange = turnover === "custom"
      ? { min: parseNumber(turnMin), max: parseNumber(turnMax) }
      : { min: turnoverOption?.min ?? null, max: turnoverOption?.max ?? null };

    try {
      const created = await api.createJob({
        projectName: finishedName.current,
        sourceUrls: sources,
        country,
        employeeRange,
        turnoverRange,
        fields,
        complianceConfirmed: confirmed,
      });
      setJobId(created.id);
      setJobMessage(created.message || "Job queued");

      let current = created;
      while (current.state === "queued" || current.state === "running") {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        current = await api.getJob(created.id);
        setProgressValue(current.progress);
        setJobMessage(current.message || "Processing source websites...");
        setStepIndex(Math.min(
          SIMULATION_STEPS.length,
          Math.floor((current.progress / 100) * SIMULATION_STEPS.length),
        ));
      }

      if (current.state === "cancelled") {
        setRunState("cancelled");
        setJobMessage(current.message || "Extraction cancelled");
        return;
      }
      if (current.state !== "completed") {
        throw new Error(current.message || "The extraction job did not complete.");
      }

      const results = await api.getResults(created.id);
      addCompanies(results.companies);
      addProject({
        id: `proj-${created.id}`,
        name: finishedName.current,
        sources,
        country,
        status: "Completed",
        progress: 100,
        recordsFound: results.companies.length,
        createdAt: new Date().toISOString().slice(0, 10),
        origin: "extracted",
      });
      setProgressValue(100);
      setStepIndex(SIMULATION_STEPS.length);
      setJobMessage(current.message || "Extraction completed");
      setRunState("done");
      showToast(`Extraction finished: ${results.companies.length} company records found.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to run extraction.";
      setRunError(message);
      setJobMessage("Extraction failed");
      setRunState("failed");
    }
  }

  async function cancelRun() {
    if (jobId) {
      try {
        await api.cancelJob(jobId);
      } catch {
        // The job may already have finished or the service may be unavailable.
      }
    }
    setRunState("cancelled");
    setJobMessage("Cancellation requested");
  }

  function resetForm() {
    setRunState("idle");
    setStepIndex(0);
    setProgressValue(0);
    setJobId(null);
    setJobMessage("");
    setRunError(null);
    setSources([]);
    setProjectName("");
    setConfirmed(false);
  }

  const progress = progressValue;

  return (
    <>
      <PageHeader title="New Extraction" description="Submit public company websites to the connected Python extraction service." />

      <div className="mb-6 flex items-start gap-3 rounded-xl border border-dashed border-warn/50 bg-warn/10 px-4 py-3 text-sm">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
        <p>
          <strong className="text-warn">Backend connection required.</strong>{" "}
          {isBackendConfigured() ? "The extraction service is configured. Only public websites that permit automated access will be processed." : "The Python backend URL is not configured yet. Extraction is disabled until the service is deployed and connected."}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <form className="space-y-6 xl:col-span-2" onSubmit={(e) => { e.preventDefault(); startExtraction(); }} noValidate>
          {/* Source websites */}
          <fieldset className="card p-5" disabled={runState !== "idle"}>
            <legend className="sr-only">Source websites</legend>
            <h2 className="mb-1 text-base font-semibold">1. Source websites</h2>
            <p className="mb-4 text-xs text-muted">Public pages or directories you are allowed to collect information from.</p>

            <label htmlFor="project-name" className="label">Project name (optional)</label>
            <input id="project-name" className="field mb-4" placeholder="e.g. Lyon logistics companies" value={projectName} onChange={(e) => setProjectName(e.target.value)} maxLength={80} />

            <label htmlFor="url-input" className="label">Website URL</label>
            <div className="flex gap-2">
              <input
                id="url-input"
                className={`field ${urlError ? "!border-bad" : ""}`}
                placeholder="https://www.example.com/directory"
                value={urlInput}
                inputMode="url"
                autoComplete="off"
                aria-invalid={urlError ? true : undefined}
                aria-describedby={urlError ? "url-error" : undefined}
                onChange={(e) => { setUrlInput(e.target.value); setUrlError(null); }}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addUrl(); } }}
              />
              <button type="button" className="btn-secondary shrink-0" onClick={addUrl}>
                <Plus className="h-4 w-4" aria-hidden /> Add
              </button>
            </div>
            {urlError && (
              <p id="url-error" role="alert" className="mt-2 flex items-center gap-1.5 text-sm text-bad">
                <AlertCircle className="h-4 w-4" aria-hidden /> {urlError}
              </p>
            )}

            {sources.length > 0 && (
              <ul className="mt-4 space-y-2" aria-label="Added source websites">
                {sources.map((s) => (
                  <li key={s} className="flex items-center gap-2 rounded-xl border border-line bg-raised px-3 py-2 text-sm">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-ok" aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{s}</span>
                    <button type="button" className="rounded-lg p-1 text-muted hover:bg-bad/10 hover:text-bad" onClick={() => setSources((cur) => cur.filter((x) => x !== s))} aria-label={`Remove ${s}`}>
                      <X className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </fieldset>

          {/* Filters */}
          <fieldset className="card p-5" disabled={runState !== "idle"}>
            <legend className="sr-only">Target criteria</legend>
            <h2 className="mb-4 text-base font-semibold">2. Target companies</h2>

            <p className="label">Country</p>
            <div className="mb-6 flex flex-wrap gap-2" role="radiogroup" aria-label="Country">
              {COUNTRY_OPTIONS.map((c) => (
                <label key={c} className={`chip ${country === c ? "chip-active" : ""}`}>
                  <input type="radio" name="country" className="sr-only" checked={country === c} onChange={() => setCountry(c)} />
                  {c}
                </label>
              ))}
            </div>

            <p className="label">Employee range</p>
            <div className="mb-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Employee range">
              {EMPLOYEE_OPTIONS.map((o) => (
                <label key={o.id} className={`chip ${employees === o.id ? "chip-active" : ""}`}>
                  <input type="radio" name="employees" className="sr-only" checked={employees === o.id} onChange={() => setEmployees(o.id)} />
                  {o.label}
                </label>
              ))}
            </div>
            {employees === "custom" && (
              <div className="mb-2 grid max-w-sm grid-cols-2 gap-2">
                <input aria-label="Minimum employees" inputMode="numeric" className="field" placeholder="Min" value={empMin} onChange={(e) => setEmpMin(e.target.value)} />
                <input aria-label="Maximum employees" inputMode="numeric" className="field" placeholder="Max" value={empMax} onChange={(e) => setEmpMax(e.target.value)} />
              </div>
            )}
            {empRangeError && <p role="alert" className="mb-2 text-sm text-bad">{empRangeError}</p>}

            <p className="label mt-6">Annual turnover</p>
            <div className="mb-2 flex flex-wrap gap-2" role="radiogroup" aria-label="Annual turnover">
              {TURNOVER_OPTIONS.map((o) => (
                <label key={o.id} className={`chip ${turnover === o.id ? "chip-active" : ""}`}>
                  <input type="radio" name="turnover" className="sr-only" checked={turnover === o.id} onChange={() => setTurnover(o.id)} />
                  {o.label}
                </label>
              ))}
            </div>
            {turnover === "custom" && (
              <div className="grid max-w-sm grid-cols-2 gap-2">
                <input aria-label="Minimum turnover in euros" inputMode="numeric" className="field" placeholder="Min €" value={turnMin} onChange={(e) => setTurnMin(e.target.value)} />
                <input aria-label="Maximum turnover in euros" inputMode="numeric" className="field" placeholder="Max €" value={turnMax} onChange={(e) => setTurnMax(e.target.value)} />
              </div>
            )}
            {turnRangeError && <p role="alert" className="mt-2 text-sm text-bad">{turnRangeError}</p>}
          </fieldset>

          {/* Fields */}
          <fieldset className="card p-5" disabled={runState !== "idle"}>
            <legend className="sr-only">Data fields</legend>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold">3. Data fields to extract</h2>
              <div className="flex gap-3 text-sm font-medium text-brand">
                <button type="button" className="hover:underline" onClick={() => setFields([...FIELD_OPTIONS])}>Select all</button>
                <button type="button" className="hover:underline" onClick={() => setFields([])}>Clear</button>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {FIELD_OPTIONS.map((f) => (
                <label key={f} className={`flex cursor-pointer items-center gap-2.5 rounded-xl border px-3 py-2.5 text-sm transition ${fields.includes(f) ? "border-brand bg-brand/10" : "border-line bg-raised hover:border-brand/50"}`}>
                  <input type="checkbox" className="h-4 w-4" checked={fields.includes(f)} onChange={() => toggleField(f)} />
                  {f}
                </label>
              ))}
            </div>
          </fieldset>

          {/* Compliance + start */}
          <div className="card p-5">
            <label className="flex cursor-pointer items-start gap-3 text-sm">
              <input type="checkbox" className="mt-0.5 h-4 w-4" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} disabled={runState !== "idle"} />
              <span>
                <span className="flex items-center gap-1.5 font-semibold"><ShieldCheck className="h-4 w-4 text-ok" aria-hidden /> I will respect the rules</span>
                <span className="text-muted">
                  I am allowed to collect information from these websites and will follow their terms of use, robots.txt, rate limits and applicable privacy laws (such as the GDPR). I will not bypass CAPTCHAs, logins or access restrictions.
                </span>
              </span>
            </label>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-muted" aria-live="polite">{problems.length > 0 && runState === "idle" ? `To continue: ${problems.join(" · ")}` : ""}</p>
              <button type="submit" className="btn-primary" disabled={!canStart}>
                <Play className="h-4 w-4" aria-hidden /> Start Extraction
              </button>
            </div>
          </div>
        </form>

        {/* Run panel */}
        <aside className="xl:sticky xl:top-24 xl:self-start" aria-label="Extraction workflow">
          <div className="card p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-base font-semibold">Workflow</h2>
              <Badge tone={runState === "failed" ? "bad" : runState === "done" ? "ok" : "brand"}>{runState === "running" ? "Running" : runState === "done" ? "Completed" : runState === "failed" ? "Failed" : runState === "cancelled" ? "Cancelled" : "Ready"}</Badge>
            </div>

            {runState === "idle" && (
              <p className="text-sm text-muted">
                {isBackendConfigured() ? "Start a job to collect permitted public company information from the source websites." : "The backend must be deployed and its URL configured before extraction can start."}
              </p>
            )}

            <ol className="mt-3 space-y-3">
              {SIMULATION_STEPS.map((label, i) => {
                const done = runState === "done" || (runState === "running" && i < stepIndex);
                const current = runState === "running" && i === stepIndex;
                return (
                  <li key={label} className={`flex items-start gap-3 text-sm ${done || current ? "text-ink" : "text-muted"}`}>
                    {done ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-ok" aria-hidden /> : current ? <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-brand" aria-hidden /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 opacity-40" aria-hidden />}
                    {label}
                  </li>
                );
              })}
            </ol>

            {runState !== "idle" && (
              <div className="mt-5">
                <div className="mb-1.5 flex justify-between text-xs text-muted"><span>Progress</span><span>{progress}%</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100} aria-label="Extraction progress">
                  <div className="h-full rounded-full bg-gradient-to-r from-brand to-accent transition-all duration-500" style={{ width: `${progress}%` }} />
                </div>
              </div>
            )}

            {runState === "running" && (
              <button className="btn-secondary mt-5 w-full" onClick={cancelRun}>Cancel extraction</button>
            )}

            {jobMessage && runState !== "idle" && <p className="mt-3 text-xs text-muted" aria-live="polite">{jobMessage}</p>}
            {runError && <p role="alert" className="mt-3 text-sm text-bad">{runError}</p>}
            {runState === "failed" && <button className="btn-secondary mt-4 w-full" onClick={resetForm}>Try again</button>}
            {runState === "cancelled" && <button className="btn-secondary mt-4 w-full" onClick={resetForm}>Configure another</button>}
            {runState === "done" && (
              <div className="mt-5 rounded-xl border border-line bg-raised p-4 text-sm">
                <p className="font-semibold">Extraction completed</p>
                <p className="mt-1 text-muted">
                  The extracted records have been added to the companies list. Review each field before using the data; B2C website matches may be empty when no clear storefront link was found.
                </p>
                <div className="mt-4 flex flex-col gap-2">
                  <Link href="/projects" className="btn-primary">Open My Projects</Link>
                  <button className="btn-secondary" onClick={resetForm}>Configure another</button>
                </div>
              </div>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}
