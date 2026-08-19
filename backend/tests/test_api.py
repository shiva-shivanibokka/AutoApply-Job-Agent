from fastapi.testclient import TestClient

import api
import job_store as js
from conftest import make_job
from ranker import keyword_score, parse_keywords

client = TestClient(api.app)


def test_keyword_score_fraction():
    job = {"title": "ML Engineer", "company": "Acme", "description": "python and pytorch"}
    assert keyword_score(job, ["python", "pytorch"]) == 1.0
    assert keyword_score(job, ["python", "rust"]) == 0.5
    assert keyword_score(job, []) == 0.0


def test_parse_keywords_splits_on_separators():
    assert parse_keywords("ml, ai; llm | nlp") == ["ml", "ai", "llm", "nlp"]
    assert parse_keywords("  ") == []


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_resume_roundtrip():
    r = client.post("/api/resume", data={"text": "python ml engineer"})
    assert r.status_code == 200 and r.json()["has_resume"] is True
    assert client.get("/api/resume").json()["text"] == "python ml engineer"


def test_patch_status_rejects_invalid():
    js.upsert_job(make_job("a"))
    assert client.patch("/api/jobs/a/status", data={"status": "bogus"}).status_code == 400


def test_patch_status_accepts_funnel_stage():
    js.upsert_job(make_job("a"))
    r = client.patch("/api/jobs/a/status", data={"status": "interviewing"})
    assert r.status_code == 200
    assert js.get_job("a")["status"] == "interviewing"


def test_refresh_requires_token():
    # No REFRESH_TOKEN configured in tests -> always forbidden.
    assert client.post("/api/refresh").status_code == 403
    assert client.post("/api/refresh", params={"token": "whatever"}).status_code == 403
