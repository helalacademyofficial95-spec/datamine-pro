# DataMine Pro

A business data-extraction dashboard. **Version 0.1 is a frontend demo**: every company in it is an invented
sample record, and the "extraction" is a clearly labelled simulation. Nothing is scraped yet.

Built with Next.js (App Router), TypeScript, Tailwind CSS, Lucide icons and ExcelJS (Excel export). All free and open source.

## What works

- Dark navy / light theme toggle, responsive sidebar (drawer on phones and tablets)
- Dashboard: 5 stat cards, activity chart, recent projects, recent companies
- New Extraction: multiple source URLs with validation, country, employee and turnover ranges (incl. custom), data fields, compliance checkbox, simulated workflow
- My Projects: search, status filter, demo projects you create
- Extracted Companies: search, sorting, filters (country, employees, turnover, verification, B2C), pagination, row selection, select all
- Data Filters: filter builder with live match count and saved presets
- Export: CSV and Excel (.xlsx) of selected records or all filtered records; Export History log
- Settings: theme, backend status, reset demo data

## Folder structure (where every file belongs)

```
datamine-pro/
├─ package.json            dependencies and commands
├─ tsconfig.json           TypeScript settings
├─ next.config.mjs         Next.js settings
├─ tailwind.config.ts      colours and theme for Tailwind
├─ postcss.config.mjs      needed by Tailwind
├─ .eslintrc.json          code-quality rules
├─ .env.example            template for the future backend address
├─ .gitignore              files Git must not upload
├─ app/                    PAGES (each folder = one URL)
│  ├─ layout.tsx           wraps every page (sidebar, theme)
│  ├─ globals.css          theme colours + shared styles
│  ├─ page.tsx             /                  Dashboard
│  ├─ new-extraction/page.tsx
│  ├─ projects/page.tsx
│  ├─ companies/page.tsx
│  ├─ filters/page.tsx
│  ├─ exports/page.tsx
│  ├─ settings/page.tsx
│  └─ not-found.tsx        404 page
├─ components/             reusable building blocks
│  ├─ layout/              Sidebar, Topbar, AppShell
│  ├─ ui/                  Badge, PageHeader, EmptyState, Toast, SettingsView …
│  ├─ dashboard/           StatCard, ActivityChart, RecentProjects, RecentCompanies, DashboardView
│  ├─ companies/           CompaniesView (table), Pagination, ExportBar, ExportHistoryView
│  ├─ extraction/          NewExtractionView, ProjectsView
│  └─ filters/             FilterPanel, FiltersView
├─ context/                shared app state (theme, filters, projects, export log)
├─ lib/                    logic with no screen: sampleData, filters, csv, export, format, extraction, nav
│  └─ api/                 typed client + types for the FUTURE Python backend
├─ backend/README.md       plan for the future Python backend (no code yet)
└─ public/                 static files (empty)
```

## 1. Install the tools (one time)

1. Install **Node.js 18.18 or newer** (the LTS version) from https://nodejs.org
2. Install **Git** from https://git-scm.com
3. Check in a terminal: `node -v` and `git --version`

## 2. Run it on your computer

Open a terminal **inside the project folder** (the one containing `package.json`) and run:

```bash
npm install
npm run dev
```

Open http://localhost:3000 in your browser. Stop the server with `Ctrl + C`.

Other useful commands:

```bash
npm run build       # production build (what Vercel runs) – run this before deploying
npm run typecheck   # checks TypeScript types
npm run lint        # checks code quality
```

If `npm install` shows "deprecated" warnings, that is normal. Only red `ERR!` messages are real problems.

## 3. Upload to GitHub

1. Create a free account at https://github.com and click **New repository**. Name it `datamine-pro`, leave it empty (no README), keep it Private or Public, then create it.
2. In the project folder run (replace `YOUR-USERNAME`):

```bash
git init
git add .
git commit -m "Initial DataMine Pro frontend"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/datamine-pro.git
git push -u origin main
```

GitHub will ask you to sign in the first time. If it asks for a password, use a Personal Access Token (GitHub → Settings → Developer settings → Tokens) or the GitHub Desktop app.

## 4. Deploy on Vercel (free Hobby plan)

1. Go to https://vercel.com and choose **Sign up → Continue with GitHub**.
2. Click **Add New… → Project** and import your `datamine-pro` repository.
3. Vercel detects Next.js automatically. Leave every setting as it is and click **Deploy**.
4. After about a minute you get a public address like `https://datamine-pro.vercel.app`.

Every time you run `git push`, Vercel redeploys automatically. No environment variables are needed for this version.

## 5. Connecting the Python backend later

Nothing needs to change in the pages. Build the service described in `backend/README.md`, copy `.env.example` to `.env.local`,
set `NEXT_PUBLIC_API_URL=http://localhost:8000`, and replace the simulation in
`components/extraction/NewExtractionView.tsx` (function `startDemoRun`) with calls to `api.createJob(...)` from `lib/api/client.ts`.
On Vercel, add the same variable under Project → Settings → Environment Variables (the backend must be hosted somewhere reachable).

## Honest notes

- All 72 companies, projects and chart numbers are generated sample data (domains end in `.example`, which can never be a real website). Sample rows carry a "Sample" badge, and exported files have a "SAMPLE DATA" column.
- Export history, demo projects and filter presets are saved in your browser only (localStorage), not on a server.
- The Excel library (ExcelJS) is loaded only when you press "Download Excel".

## Troubleshooting

- **Port already in use:** run `npm run dev -- -p 3001`.
- **`npm` not recognised:** reinstall Node.js and reopen the terminal.
- **Weird errors after changing versions:** delete the `node_modules` folder and `.next` folder, then run `npm install` again.

## Enrichment queue: recovery and resume

- The queue lives in Neon (`enrichment_queue`); nothing is held only in memory.
- Workers claim small batches (`QUEUE_BATCH_SIZE`, default 10) with `FOR UPDATE SKIP LOCKED` and renew their lease every minute.
- A `processing` row is treated as abandoned only after `QUEUE_STALE_MINUTES` (default 15) without a heartbeat. It is then retried, or marked `failed` if its 3 attempts are used up. Fresh leases are never touched.
- After a restart or Render wake-up, the worker resumes on startup and whenever `GET /enrichment/status` is polled (no token needed; it only drains existing queue rows).
- A company is marked `done` only when discovery really ran. If Wikidata/OpenStreetMap failed or the registry site was unreachable, the result is saved as inconclusive (`discoveryComplete: false`, `sourceErrors`) and the row is retried with backoff.
- `POST /enrichment/queue/requeue-failed` (admin token) gives failed rows a fresh set of attempts.
- Discovery sources: registry website, Wikidata (by SIREN), OpenStreetMap/Nominatim (name + postcode/city), and domain guesses verified on the site itself. A general web-search provider is not configured (it needs an API key), so companies without a Wikidata/OSM entry or a guessable domain stay "Not Found".

### Source failures and retries

- A public source that **refuses** access (HTTP 401/403/451, e.g. Wikidata from some hosts) is recorded in `sourcesBlocked`. It is not retried per company and is never treated as proof that no website exists.
- A **transient** failure (timeout, 429, 5xx) is retried with bounded exponential backoff inside the lookup, then makes the result inconclusive so the queue retries it (30s, 60s, 120s... max 15 min, 3 attempts).
- Failed rows with transient causes are automatically given a fresh set of attempts after 30 minutes, at most 3 times (`cycles` column, added with `ADD COLUMN IF NOT EXISTS`). Errors starting with `permanent:` are never retried. `/enrichment/status` lists failures grouped by cause (`queue.failedByCause`).
- Ownership checks use the national identifier of each country: SIREN/SIRET (France), KBO/BCE enterprise number (Belgium), RCS `B` number (Luxembourg). OSM searches are scoped to the company's country.

### Coverage, preservation and keep-awake

- `GET /enrichment/status` returns `coverage` computed from Neon: `enriched`, `officialWebsites`, `officialWebsitesVerified`, `b2cWebsites`, `emails`, `phones`, plus `companies` and `directors` from the extraction records (cached 60 s). Candidate URLs are never counted, only Verified/Partially Verified results.
- A re-check never replaces a stronger stored result with a weaker one (`preserve_better`; marked `preservedFromPrevious`).
- When a site's home page links no legal notice, `/mentions-legales` and `/legal` are tried; up to 10 name-derived domains are tested, each accepted only after on-site verification.
- `.github/workflows/keepalive.yml` polls `/enrichment/status` every 10 minutes so Render Free stays awake and the worker resumes the queue. It uses no secrets.
