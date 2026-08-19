# HireView

**A first-party job aggregator and application tracker.** HireView searches the ATS platforms companies actually hire on — Greenhouse, Lever, and Ashby — across 1,000+ companies at once, then lets you track every role you care about through a full application pipeline. Every result links straight to the company's own application form.

It is **not** a job board. It hosts no listings. There are no reposts, no recruiter spam, and no expired "ghost jobs" — because every result is scraped live from the company's own hiring system.

> ### ▶ Runs locally. There is no hosted demo, and that is deliberate.
>
> HireView is **single-tenant by design**: one database, one resume, one pipeline,
> no authentication. That is the right shape for a personal job-search tool and
> the wrong shape for a public URL — a shared instance would serve one person's
> resume to every visitor and let anyone edit their pipeline.
>
> Adding real multi-user auth would roughly double the project without making the
> interesting parts (the parallel ATS fan-out, the BM25 fit ranking) any better,
> so it is intentionally out of scope.
>
> **Deploying it is still fully supported** — the container, the config, and the
> cloud data path all ship in this repo and are exercised by CI. See
> [Deploying it yourself](#deploying-it-yourself). Just run your own instance
> rather than sharing one.
>
> **[→ Local setup](#local-development)** takes about two minutes.

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
- **Auto-close** — a scheduled job rechecks every tracked posting in parallel and flags it closed once it 404s. Only an explicit "gone" closes a job; a network error leaves it alone.
- **Daily email digest** — re-runs your last search, scores the results the same way an interactive search would, and emails whatever is genuinely new.

---

## Architecture

Two processes, talking over HTTP. The only thing that changes between running it
on your laptop and running it on a cloud host is **where three environment
variables point** — there is no separate "production mode" in the code.

```
┌────────────────────┐        ┌──────────────────────┐        ┌────────────────┐
│  Next.js 15 (React)│  HTTP  │   FastAPI backend    │ libsql │   SQLite file  │
│  route handlers    │ ─────▶ │   scraper · ranker   │ ─────▶ │       or       │
│  (BACKEND_URL)     │  proxy │   refresh (digest)   │        │  Turso (cloud) │
└────────────────────┘        └──────────┬───────────┘        └────────────────┘
     :3000                          :8000 │ scrape
                             Greenhouse · Lever · Ashby · Adzuna
                                          ▲ daily trigger (optional)
                                    any cron → POST /api/refresh?token=
```

- **Frontend** proxies every `/api/*` call through a Next.js route handler
  (`lib/backend.ts` → `BACKEND_URL`), so the browser only ever talks to its own
  origin. No CORS in the browser, and the backend URL is never exposed to it.
- **Persistence** is `libsql`: a local SQLite file when `TURSO_DATABASE_URL` is
  blank, Turso (cloud SQLite) when it is set. **One code path, switched by env** —
  which is why the local and deployed behaviour cannot drift apart.
- **Scraper** routes every network call through a logging `_get()` helper, fans
  out across companies in a thread pool, and enforces a hard wall-clock deadline
  per source. A dead board is logged, never silently swallowed, and never hangs
  or crashes a search.
- **Scoring** lives entirely in `ranker.py`. Both write paths — interactive search
  and the daily digest — call the same `score_jobs()`, so a posting cannot score
  differently depending on which one found it.

### Tech stack

**Backend:** Python 3.12 · FastAPI · uvicorn · libsql · BeautifulSoup · rank-bm25
**Frontend:** Next.js 15 · React 19 · TypeScript · Tailwind CSS 4
**Ships for deployment:** Dockerfile · Turso data path · GitHub Actions CI

---

## Local development

Two terminals. No accounts, no API keys, no cloud services — the defaults give
you a working app on a local SQLite file.

**Terminal 1 — backend** (from `backend/`):

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt                 # runtime + test deps
cp .env.example .env                                # leave TURSO_* blank for local SQLite
uvicorn api:app --reload --port 8000
```

**Terminal 2 — frontend** (from `frontend/`):

```bash
npm install
npm run dev            # http://localhost:3000
```

Open **http://localhost:3000**. Search a job title, save a result, and it appears
under **My Pipeline**. Paste your resume in the search panel to switch ranking
from keyword match to BM25 resume fit.

The database is created on first run at `backend/data/jobs.db` and is gitignored,
along with `.env`. Delete the file to start clean.

Interactive API docs (OpenAPI/Swagger) are auto-generated at
`http://localhost:8000/docs`.

---

## Configuration

All backend config lives in `backend/.env` (see `.env.example`) and is read in
exactly one place, `config.py`, which validates it at startup — an inconsistent
combination fails loudly on boot rather than at some later request.

| Variable | Purpose | Needed locally? |
|---|---|---|
| `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | Turso connection. **Both blank = local SQLite file.** Setting one without the other is a startup error. | No |
| `FRONTEND_ORIGINS` | Comma-separated CORS allow-list. Defaults to `localhost:3000,3001`. | No |
| `LOG_LEVEL` | `INFO` / `DEBUG` / … | No |
| `REFRESH_TOKEN` | Shared secret for the `POST /api/refresh` trigger. **Unset ⇒ the endpoint refuses every call**, which is the safe default. | No |
| `SMTP_USER`, `SMTP_PASS`, `DIGEST_TO` | Gmail app password + recipient for the digest email. The digest is skipped unless all three are set. | No |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Optional extra source. Keys typed into the UI take precedence; these are the fallback, and the only way the scheduled digest can use Adzuna. | No |

Frontend: `BACKEND_URL`, defaulting to `http://localhost:8000`.

**Everything above is optional for local use.** Copy `.env.example` to `.env` and
change nothing, and you get a working app on a local SQLite file.

---

## Deploying it yourself

Not deployed anywhere by the author — see the note at the top — but the repo is
built to be, and nothing about the deployment path is stubbed or theoretical:

| Piece | Ships in this repo |
|---|---|
| Container | `backend/Dockerfile` — non-root user, binds `$PORT`, `exec`s uvicorn so it receives signals. Works unmodified on Cloud Run, Render, Fly, Railway, or any container host. |
| Cloud data | `job_store.py` speaks `libsql`, which is SQLite locally and Turso in the cloud. **Same code path**, chosen by env — so a container with an ephemeral filesystem keeps its data. |
| Frontend | Next.js route handlers already read `BACKEND_URL`; no code change to point them at a remote backend. Vercel-ready with root directory `frontend`. |
| Scheduled work | `POST /api/refresh?token=` is a plain HTTP endpoint — drive it from any cron (Cloud Scheduler, GitHub Actions, cron-job.org). |
| CI | `.github/workflows/ci.yml` runs ruff + pytest + tsc + `next build` on every push. |
| Deploy automation | `.github/workflows/deploy-backend.yml` — a manual Cloud Run deploy. Add `GCP_PROJECT_ID` and `GCP_SA_KEY` secrets and run it from the Actions tab. Delete it if you deploy elsewhere. |

**The order that matters:** create the Turso DB → deploy the backend with
`TURSO_*` and `REFRESH_TOKEN` set → deploy the frontend with `BACKEND_URL`
pointing at it → set `FRONTEND_ORIGINS` to the frontend's real URL and redeploy
the backend. The last step closes the CORS loop and needs a URL that only exists
after step three.

**One caution.** There is no authentication. A single shared instance means one
resume and one pipeline visible to everyone who finds the URL, and `/api/search`
will fan out across hundreds of ATS boards for any anonymous caller. Deploy it
for yourself, behind your host's access control, or add auth and per-user rows
first.

---

## API

Interactive docs are generated at `http://localhost:8000/docs`.

| Method | Endpoint | |
|---|---|---|
| POST | `/api/search` | Scrape enabled sources, score, persist, return results |
| GET | `/api/jobs?status=&sort=&limit=` | List jobs (`status=tracked` = whole pipeline). Capped at 500 rows per request |
| GET | `/api/jobs/{id}` | Single job |
| POST | `/api/jobs/{id}/fetch-description` | Fetch full JD text |
| PATCH | `/api/jobs/{id}/status` | Move through the pipeline funnel |
| GET/POST | `/api/resume` | Read / save resume text for BM25 ranking (100k char limit) |
| GET | `/api/companies`, `/api/suggestions` | Autocomplete |
| POST | `/api/refresh?token=` | Auto-close + digest. Requires `REFRESH_TOKEN`; refuses every call if it is unset |
| GET | `/api/health` | Health check |

Every `/api/*` path is mirrored by a Next.js route handler under `frontend/app/api/`,
so the browser only ever calls its own origin. **A backend endpoint the browser
needs but the frontend has no handler for will not work once deployed**, even
though it works in local development.

---

## Testing & CI

```bash
cd backend && pytest -q      # 30 tests: store, ranker, scraper, api, regressions
ruff check .                 # lint
cd frontend && npx tsc --noEmit && npm run build
```

GitHub Actions (`.github/workflows/ci.yml`) runs backend `ruff` + `pytest` and frontend typecheck + build on every push and PR.

`tests/test_regressions.py` pins one test per bug found in the August 2026 audit.
They are kept in their own file deliberately: every one of them passed code
review *and* the existing suite while the underlying bug was live, so they are
named after the defect rather than folded in with the feature tests.

There is no frontend unit-test framework — `tsc --noEmit` plus a real
`next build` are the gate. That is a deliberate choice, not an omission.

---

## Project structure

```
backend/
  api.py          FastAPI app + endpoints
  scraper.py      multi-source scraping; _get() logs failures, parallel fan-out
                  with a hard per-source wall-clock deadline
  job_store.py    libsql persistence — local SQLite file or Turso, one code path
  ranker.py       all scoring: keyword match, BM25 resume fit, and the blend
                  both write paths share
  refresh.py      auto-close (parallel) + daily digest email
  config.py       every env var, read once, validated at startup
  tests/          pytest suite (+ test_regressions.py, one test per fixed bug)
  Dockerfile      non-root, binds $PORT — deployable as-is
frontend/
  app/api/        one route handler per backend endpoint the browser calls
  components/     HireView, SearchBar, JobGrid, JobModal, PipelineBoard
  lib/            api client, types, status funnel, sponsorship, backend URL
```

**No rewrites in `next.config.ts`, on purpose.** Array-form rewrites are matched
before dynamic routes, so a catch-all `/api/:path*` rule silently shadows the
route handlers for `/api/jobs` and `/api/jobs/[id]/*`. That is invisible in local
development, where the rewrite target is the real backend, and breaks the entire
tracker once deployed. Route handlers only.
