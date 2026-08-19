"""
config.py
Central configuration + startup validation for HireView.

Read every environment variable in ONE place so nothing reads os.getenv ad hoc,
and fail loudly at startup (validate()) instead of silently later at runtime.

Data layer:
  - If TURSO_DATABASE_URL is set  -> connect to Turso (cloud SQLite) in production.
  - If it is empty                -> fall back to a local SQLite file for dev.
    Both use the same `libsql` driver, so there is exactly one code path.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# --- Data ---
TURSO_DATABASE_URL = _env("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = _env("TURSO_AUTH_TOKEN")
USE_TURSO = bool(TURSO_DATABASE_URL)
# HIREVIEW_DB_PATH overrides the local SQLite location (used by tests for a temp DB).
LOCAL_DB_PATH = Path(_env("HIREVIEW_DB_PATH") or (Path(__file__).parent / "data" / "jobs.db"))

# --- Web ---
# Comma-separated list of origins allowed to call the API (the deployed frontend).
FRONTEND_ORIGINS = [
    o.strip()
    for o in _env(
        "FRONTEND_ORIGINS", "http://localhost:3000,http://localhost:3001"
    ).split(",")
    if o.strip()
]

# --- Logging ---
LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()

# --- Scheduled refresh + daily digest ---
# Shared secret Cloud Scheduler sends as ?token= to trigger POST /api/refresh.
REFRESH_TOKEN = _env("REFRESH_TOKEN")
# Gmail SMTP (app password) for the digest email. All optional — digest is
# skipped if SMTP_USER/SMTP_PASS/DIGEST_TO are not all set.
SMTP_HOST = _env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_env("SMTP_PORT", "465"))
SMTP_USER = _env("SMTP_USER")
SMTP_PASS = _env("SMTP_PASS")
DIGEST_TO = _env("DIGEST_TO")
DIGEST_ENABLED = bool(SMTP_USER and SMTP_PASS and DIGEST_TO)

# --- Adzuna (optional extra source) ---
# Used when the UI leaves the key fields blank, and by the daily digest, which
# has no UI to read them from. Documented in .env.example and the README since
# the beginning, but nothing actually read them until now.
ADZUNA_APP_ID = _env("ADZUNA_APP_ID")
ADZUNA_APP_KEY = _env("ADZUNA_APP_KEY")


def validate() -> None:
    """Raise on inconsistent config. Called once at API startup."""
    if TURSO_DATABASE_URL and not TURSO_AUTH_TOKEN:
        raise RuntimeError(
            "TURSO_DATABASE_URL is set but TURSO_AUTH_TOKEN is missing. "
            "Set both (Turso) or neither (local SQLite)."
        )
    if not FRONTEND_ORIGINS:
        raise RuntimeError("FRONTEND_ORIGINS resolved to an empty list.")
