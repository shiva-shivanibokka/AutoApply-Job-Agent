"""
One test per bug found in the August 2026 audit.

Each of these passed review and passed the existing suite while being broken —
that's why they're pinned here by name rather than folded into the other files.
"""

from conftest import make_job
from fastapi.testclient import TestClient

import api
import job_store as js
from ranker import score_jobs

client = TestClient(api.app)


def test_company_without_slug_is_rejected_not_a_500():
    """A dict missing "slug" raised KeyError inside the scraper -> HTTP 500."""
    r = client.post(
        "/api/search",
        data={"keywords": "engineer", "companies": '[{"platform":"greenhouse"}]'},
    )
    assert r.status_code != 500, r.text


def test_malformed_companies_json_is_a_400_not_a_silent_full_fanout():
    """
    Unparseable JSON used to be swallowed, turning a targeted search into an
    unrequested fan-out across every known board.
    """
    r = client.post("/api/search", data={"keywords": "ml", "companies": "{not json"})
    assert r.status_code == 400
    assert "json" in r.json()["detail"].lower()

    r = client.post("/api/search", data={"keywords": "ml", "companies": '{"a":1}'})
    assert r.status_code == 400


def test_score_jobs_is_the_single_definition_of_match_score():
    """
    The digest path scored nothing, so the same posting got match_score 0 there
    and a real score via /api/search. Both now call score_jobs.
    """
    jobs = [
        {"title": "ML Engineer", "company": "Acme", "description": "python pytorch"},
        {"title": "Chef", "company": "Bistro", "description": "knife service"},
    ]
    score_jobs(jobs, ["python", "pytorch"])
    assert jobs[0]["match_score"] == 1.0
    assert jobs[1]["match_score"] == 0.0

    # With a resume, the blend must stay in range and still favour the match.
    score_jobs(jobs, ["python"], "python pytorch machine learning engineer")
    assert 0.0 <= jobs[1]["match_score"] < jobs[0]["match_score"] <= 1.0


def test_list_jobs_is_bounded():
    """limit=0 used to mean "no limit" and returned the whole table."""
    for i in range(5):
        js.upsert_job(make_job(f"j{i}"))
    assert len(client.get("/api/jobs", params={"limit": 2}).json()["jobs"]) == 2
    # limit=0 and a limit past the ceiling both clamp instead of unbounding.
    assert len(client.get("/api/jobs", params={"limit": 0}).json()["jobs"]) == 5
    assert len(client.get("/api/jobs", params={"limit": 10_000}).json()["jobs"]) == 5


def test_oversized_resume_is_rejected():
    r = client.post("/api/resume", data={"text": "x" * (api.MAX_RESUME_CHARS + 1)})
    assert r.status_code == 413


def test_title_suggestions_do_not_treat_percent_as_a_wildcard():
    """An unescaped LIKE pattern let "%" match every row."""
    js.upsert_job(make_job("a", title="Machine Learning Engineer"))
    assert js.suggest_titles("%") == []
    assert js.suggest_titles("Machine") == ["Machine Learning Engineer"]


def test_adzuna_keys_are_actually_read_from_env():
    """These were documented in .env.example and the README but never read."""
    assert hasattr(api.config, "ADZUNA_APP_ID")
    assert hasattr(api.config, "ADZUNA_APP_KEY")
