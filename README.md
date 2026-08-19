# HireView

**A first-party job aggregator and application tracker.** HireView searches the ATS platforms companies actually hire on — Greenhouse, Lever, and Ashby — across 1,000+ companies at once, then lets you track every role you care about through a full application pipeline. Every result links straight to the company's own application form.

It is **not** a job board. It hosts no listings. There are no reposts, no recruiter spam, and no expired "ghost jobs" — because every result is scraped live from the company's own hiring system.

---

## Why it's different from LinkedIn / Indeed / Simplify

| | The big sites | **HireView** |
|---|---|---|
| Source of jobs | Aggregated, often reposted/stale | **First-party ATS boards**, live |
| Ghost jobs | Common | Auto-closed once the posting 404s |
| Freshness | Opaque | **"New since last look"** flagged per search |
| Your funnel | Not tracked (LinkedIn) | **Full pipeline**: saved → applied → interviewing → offer/rejected |
| Fit ranking | Keyword-ish | **BM25 resume-fit** ranking, no heavyweight ML |
| Early-career | Buried | First-class new-grad / intern / **sponsorship** filters |

---

## Features

- **Multi-source search** — Greenhouse, Lever, Ashby (+ optional Adzuna), fanned out in parallel with a hard wall-clock deadline so a search never hangs.
- **Multi-select title & company search** with autocomplete backed by a live [SimplifyJobs](https://github.com/SimplifyJobs) dataset (1,000+ companies) plus a curated fallback list.
- **Filters** — experience level (intern → staff), job type, date posted, location, and a **visa-sponsorship** heuristic (hide roles that exclude sponsorship, or show only explicit sponsors).
- **Resume-fit ranking** — paste your resume once; jobs are ranked by BM25 relevance to it, blended with keyword match. Pure-lexical, so no gigabytes of ML in the image.
- **Application pipeline tracker** — move a job through `saved → applied → interviewing → offer/rejected`; the **My Pipeline** view loads your tracked jobs from the database so they persist across searches.
- **"New since last look"** — jobs first seen in your latest search are flagged, with a running count.
- **Auto-close** — a daily job rechecks each tracked posting and flags it closed if it's gone.
- **Daily email digest** — re-runs your last search and emails brand-new matches.

---

## Architecture

```
┌────────────────────┐        ┌──────────────────────┐        ┌───────────────┐
│  Next.js 15 (React)│  HTTP  │   FastAPI backend    │  libsql│     Turso     │
│  Vercel            │ ─────▶ │   Google Cloud Run   │ ─────▶ │ (cloud SQLite)│
│  route handlers    │  proxy │   scraper · ranker   │        └───────────────┘
│  (BACKEND_URL)     │        │   refresh (digest)   │
└────────────────────┘        └──────────┬───────────┘
                                          │ scrape
                             Greenhouse · Lever · Ashby · Adzuna
                                          ▲ daily trigger
                                  Cloud Scheduler → POST /api/refresh
```

- **Frontend** proxies all `/api/*` calls to the backend through Next.js route handlers (`lib/backend.ts` → `BACKEND_URL`), so the browser stays same-origin.
- **Persistence** is `libsql` — a local SQLite file in dev, **Turso** (cloud SQLite) in production. One code path; switched by env. This is why redeploys don't wipe your data.
- **Scraper** routes every network call through a logging `_get()` helper; a dead board is logged, not silently swallowed, and never crashes the search.

### Tech stack

**Backend:** Python 3.12 · FastAPI · uvicorn · libsql · BeautifulSoup · rank-bm25
**Frontend:** Next.js 15 · React 19 · TypeScript · Tailwind CSS 4
**Infra:** Google Cloud Run · Vercel · Turso · Cloud Scheduler · GitHub Actions

---

## Local development

**Backend** (from `backend/`):

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                 # runtime + test deps
cp .env.example .env                                # leave TURSO_* blank for local SQLite
uvicorn api:app --reload --port 8000
```

Interactive API docs (OpenAPI/Swagger) are auto-generated at `http://localhost:8000/docs`.

**Frontend** (from `frontend/`):

```bash
npm install
npm run dev            # http://localhost:3000
```

---

## Configuration

All backend config lives in `backend/.env` (see `.env.example`) and is validated at startup — the app fails loudly if it's inconsistent.

| Variable | Purpose |
|---|---|
| `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | Turso connection. **Blank = local SQLite** (dev). |
| `FRONTEND_ORIGINS` | Comma-separated CORS allow-list (your deployed frontend URL). |
| `LOG_LEVEL` | `INFO` / `DEBUG` / … |
| `REFRESH_TOKEN` | Shared secret for the daily `POST /api/refresh` trigger. |
| `SMTP_USER`, `SMTP_PASS`, `DIGEST_TO` | Gmail app password + recipient for the email digest (all optional). |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Optional extra source (also enterable in the UI). |

Frontend: `BACKEND_URL` (the Cloud Run URL in production; defaults to `http://localhost:8000`).

---

## Deployment ($0 stack)

- **Frontend → Vercel.** Import the repo, set root directory to `frontend`, add env `BACKEND_URL=<your Cloud Run URL>`. Vercel auto-deploys on push.
- **Backend → Google Cloud Run.** Deploy `backend/` (it has a `Dockerfile`); set env vars (`TURSO_*`, `FRONTEND_ORIGINS`, `REFRESH_TOKEN`, `SMTP_*`) on the service. A manual GitHub Actions workflow (`Deploy backend (Cloud Run)`) is included — add `GCP_PROJECT_ID` and `GCP_SA_KEY` secrets and run it from the Actions tab.
- **Data → Turso.** `turso db create hireview`, then set `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` on Cloud Run.
- **Daily digest → Cloud Scheduler.** Create a job that `POST`s `https://<cloud-run-url>/api/refresh?token=<REFRESH_TOKEN>` on your schedule.

> Cloud Run scales to zero, so the first request after idle has a ~2–5s cold start — expected for a personal tool.

---

## API

| Method | Endpoint | |
|---|---|---|
| POST | `/api/search` | Scrape enabled sources, score, persist, return results |
| GET | `/api/jobs?status=` | List jobs (`status=tracked` = whole pipeline) |
| GET | `/api/jobs/{id}` | Single job |
| POST | `/api/jobs/{id}/fetch-description` | Fetch full JD text |
| PATCH | `/api/jobs/{id}/status` | Move through the pipeline funnel |
| GET/POST | `/api/resume` | Read / save resume text for BM25 ranking |
| GET | `/api/companies`, `/api/suggestions` | Autocomplete |
| POST | `/api/refresh?token=` | Auto-close + digest (Cloud Scheduler) |
| GET | `/api/health` | Health check |

---

## Testing & CI

```bash
cd backend && pytest -q      # 30 tests: store, ranker, scraper, api, regressions
ruff check .                 # lint
cd frontend && npx tsc --noEmit && npm run build
```

GitHub Actions (`.github/workflows/ci.yml`) runs backend `ruff` + `pytest` and frontend typecheck + build on every push and PR.

---

## Project structure

```
backend/
  api.py          FastAPI app + endpoints
  scraper.py      multi-source scraping, _get() with failure logging
  job_store.py    libsql persistence (local SQLite / Turso)
  ranker.py       BM25 resume-fit scoring
  refresh.py      auto-close + daily digest
  config.py       central env + startup validation
  tests/          pytest suite
  Dockerfile
frontend/
  app/            Next.js routes + API proxy handlers
  components/     HireView, SearchBar, JobGrid, JobModal, PipelineBoard
  lib/            api client, types, status funnel, sponsorship, backend URL
```
