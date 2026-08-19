"""
HireView — FastAPI Backend

Endpoints:
  POST /api/search                       — scrape jobs, save to SQLite, return all results
  GET  /api/jobs                         — list saved jobs (optional status + sort filters)
  GET  /api/jobs/{id}                    — get single job detail
  POST /api/jobs/{id}/fetch-description  — fetch full JD text from URL
  PATCH /api/jobs/{id}/status            — update job status
  GET  /api/health                       — health check

Run:
  cd backend
  uvicorn api:app --reload --port 8000
"""

import json as _json
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from job_store import (
    get_job,
    get_jobs,
    get_setting,
    set_setting,
    suggest_titles,
    update_job_status,
    upsert_job,
)
from ranker import parse_keywords, score_jobs
from scraper import fetch_job_description, get_company_name_map, search_jobs

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("hireview")

# Application pipeline funnel. "new" = untracked; "dismissed" = hidden.
VALID_STATUSES = {
    "new",
    "saved",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "dismissed",
}

CURATED_TITLES = [
    "Machine Learning Engineer",
    "ML Engineer",
    "Senior ML Engineer",
    "Staff Machine Learning Engineer",
    "Principal ML Engineer",
    "ML Research Scientist",
    "Research Scientist",
    "Applied Scientist",
    "AI Engineer",
    "AI Research Engineer",
    "AI/ML Engineer",
    "Data Scientist",
    "Senior Data Scientist",
    "Staff Data Scientist",
    "Data Engineer",
    "Senior Data Engineer",
    "Analytics Engineer",
    "Data Analyst",
    "Business Intelligence Analyst",
    "BI Engineer",
    "Software Engineer",
    "Senior Software Engineer",
    "Staff Software Engineer",
    "Principal Software Engineer",
    "Software Engineer II",
    "Software Engineer III",
    "Backend Engineer",
    "Frontend Engineer",
    "Full Stack Engineer",
    "Full Stack Developer",
    "Backend Developer",
    "Frontend Developer",
    "Platform Engineer",
    "Infrastructure Engineer",
    "Site Reliability Engineer",
    "DevOps Engineer",
    "Cloud Engineer",
    "Solutions Engineer",
    "ML Platform Engineer",
    "ML Infrastructure Engineer",
    "LLM Engineer",
    "Generative AI Engineer",
    "AI Product Engineer",
    "Prompt Engineer",
    "NLP Engineer",
    "Computer Vision Engineer",
    "Robotics Engineer",
    "Autonomous Systems Engineer",
    "Deep Learning Engineer",
    "Reinforcement Learning Engineer",
    "Quantitative Researcher",
    "Quantitative Analyst",
    "Quant Developer",
    "Product Manager",
    "Senior Product Manager",
    "Technical Product Manager",
    "Product Designer",
    "UX Designer",
    "UI Designer",
    "UX Researcher",
    "Engineering Manager",
    "Director of Engineering",
    "VP of Engineering",
    "Head of Data Science",
    "Head of AI",
    "Head of Machine Learning",
    "Research Engineer",
    "Applied Research Engineer",
    "Research Intern",
    "Software Engineer Intern",
    "Data Science Intern",
    "ML Intern",
    "Data Engineering Intern",
    "Product Intern",
    "Security Engineer",
    "Security Analyst",
    "Application Security Engineer",
    "Embedded Systems Engineer",
    "Firmware Engineer",
    "Systems Engineer",
    "iOS Engineer",
    "Android Engineer",
    "Mobile Engineer",
    "New Grad Software Engineer",
    "New Grad Data Scientist",
    "New Grad ML Engineer",
    "Associate Software Engineer",
    "Associate Data Scientist",
    "Technical Program Manager",
    "Program Manager",
    "Project Manager",
    "Solutions Architect",
    "Enterprise Architect",
    "Technical Architect",
    "Marketing Manager",
    "Growth Engineer",
    "Growth Analyst",
    "Financial Analyst",
    "Business Analyst",
    "Operations Analyst",
    "Recruiter",
    "Technical Recruiter",
    "HR Business Partner",
    "Content Writer",
    "Technical Writer",
    "Developer Advocate",
]

config.validate()  # fail loudly at startup on bad config
log.info(
    "HireView starting: data=%s, origins=%s",
    "turso" if config.USE_TURSO else "local-sqlite",
    config.FRONTEND_ORIGINS,
)

app = FastAPI(title="HireView API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/companies")
async def companies(q: str = "", limit: int = 10):
    """
    Return company name suggestions matching the query.
    Each result includes the display name, ATS platform, and slug.
    """
    if not q.strip():
        return {"companies": []}
    q_lower = q.lower()
    name_map = get_company_name_map()
    matches = [
        {"name": name, "platform": info["platform"], "slug": info["slug"]}
        for name, info in name_map.items()
        if q_lower in name.lower()
    ]
    matches.sort(key=lambda c: (not c["name"].lower().startswith(q_lower), c["name"]))
    return {"companies": matches[:limit]}


@app.get("/api/suggestions")
async def suggestions(q: str = "", limit: int = 8):
    """
    Return job title suggestions matching the query.
    Merges curated titles with titles seen in past searches (from DB).
    """
    if not q.strip():
        return {"suggestions": []}
    q_lower = q.lower()
    curated = [t for t in CURATED_TITLES if q_lower in t.lower()][:limit]
    from_db = suggest_titles(q, limit)
    combined = list({t: None for t in curated + from_db}.keys())[:limit]
    return {"suggestions": combined}


@app.post("/api/search")
async def search(
    keywords: str = Form(""),
    location: str = Form(""),
    adzuna_app_id: str = Form(""),
    adzuna_app_key: str = Form(""),
    use_greenhouse: str = Form("true"),
    use_lever: str = Form("true"),
    use_ashby: str = Form("true"),
    companies: str = Form(""),  # JSON array of {name, platform, slug}
):
    """
    Scrape all enabled sources, score by keyword relevance, persist to SQLite,
    and return all results sorted newest first.
    """
    kw_list = parse_keywords(keywords)

    target_companies: list | None = None
    if companies.strip():
        # Say so when this is malformed. Swallowing it silently turned a targeted
        # 3-company search into an unrequested fan-out over every known board,
        # which looks like a hang rather than a bad request.
        try:
            parsed = _json.loads(companies)
        except ValueError as e:
            raise HTTPException(400, f"companies must be a JSON array: {e}")
        if not isinstance(parsed, list):
            raise HTTPException(400, "companies must be a JSON array")
        if parsed:
            target_companies = parsed

    if not keywords.strip() and not target_companies:
        return {
            "jobs": [],
            "total": 0,
            "message": "Enter at least one job title or company.",
        }

    raw_jobs = search_jobs(
        keywords=keywords,
        location=location,
        # UI-entered keys win; fall back to the env-configured pair.
        adzuna_app_id=adzuna_app_id or config.ADZUNA_APP_ID,
        adzuna_app_key=adzuna_app_key or config.ADZUNA_APP_KEY,
        use_greenhouse=(use_greenhouse.lower() == "true"),
        use_lever=(use_lever.lower() == "true"),
        use_ashby=(use_ashby.lower() == "true"),
        target_companies=target_companies,
    )

    if not raw_jobs:
        return {
            "jobs": [],
            "total": 0,
            "message": "No jobs found. Try different keywords or enable more sources.",
        }

    # Keyword relevance, blended with BM25 resume fit when a resume is saved.
    score_jobs(raw_jobs, kw_list, get_setting("resume") or "")

    new_count = 0
    for job in raw_jobs:
        is_new = upsert_job(job)
        job["is_new"] = is_new
        if is_new:
            new_count += 1

    def _sort_key(j: dict) -> str:
        s = j.get("posted_at") or j.get("scraped_at", "")
        if not s:
            return ""
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()
        except Exception:
            return s

    raw_jobs.sort(key=_sort_key, reverse=True)

    # Remember this search so the daily digest can re-run it (Adzuna keys excluded).
    set_setting(
        "last_search",
        _json.dumps({
            "keywords": keywords,
            "location": location,
            "use_greenhouse": use_greenhouse.lower() == "true",
            "use_lever": use_lever.lower() == "true",
            "use_ashby": use_ashby.lower() == "true",
            "companies": target_companies,
        }),
    )

    return {"jobs": raw_jobs, "total": len(raw_jobs), "new_count": new_count}


MAX_PAGE = 500  # ceiling on rows one request can pull back
MAX_RESUME_CHARS = 100_000  # ~40 pages; a real resume is under 10k


@app.get("/api/jobs")
async def list_jobs(
    status: Optional[str] = None,
    sort: str = "newest",  # "newest" | "relevance"
    limit: int = 0,  # 0 = server default (MAX_PAGE)
):
    # Bounded either way: limit=0 used to mean "no limit" and returned the whole table.
    limit = MAX_PAGE if limit <= 0 else min(limit, MAX_PAGE)
    return {"jobs": get_jobs(status=status, sort=sort, limit=limit)}


@app.get("/api/jobs/{job_id}")
async def get_job_detail(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.post("/api/jobs/{job_id}/fetch-description")
async def fetch_description(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    url = job.get("url", "")
    if not url:
        raise HTTPException(400, "Job has no URL")

    text = fetch_job_description(url)
    if not text:
        raise HTTPException(
            422, "Could not extract JD text from this URL. The page may require login."
        )

    job["description"] = text
    upsert_job(job)
    return {"description": text}


@app.patch("/api/jobs/{job_id}/status")
async def patch_status(job_id: str, status: str = Form(...)):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if status not in VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(VALID_STATUSES)}")
    update_job_status(job_id, status)
    return {"job_id": job_id, "status": status}


@app.post("/api/resume")
async def save_resume(text: str = Form("")):
    """Store the user's resume text; used to rank jobs by fit (BM25)."""
    text = text.strip()
    if len(text) > MAX_RESUME_CHARS:
        raise HTTPException(
            413, f"resume too long ({len(text)} chars, max {MAX_RESUME_CHARS})"
        )
    set_setting("resume", text)
    return {"has_resume": bool(text), "length": len(text)}


@app.get("/api/resume")
async def read_resume():
    text = get_setting("resume") or ""
    return {"text": text, "has_resume": bool(text), "length": len(text)}


@app.post("/api/refresh")
async def refresh(token: str = ""):
    """
    Daily maintenance trigger for Cloud Scheduler: auto-close tracked jobs whose
    posting is gone, and email a digest of new matches. Protected by REFRESH_TOKEN.
    """
    if not config.REFRESH_TOKEN or token != config.REFRESH_TOKEN:
        raise HTTPException(403, "invalid or missing refresh token")
    from refresh import run_refresh

    summary = run_refresh()
    log.info("refresh done: %s", summary)
    return summary


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "HireView API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
