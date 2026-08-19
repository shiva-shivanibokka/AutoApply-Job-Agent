"""
refresh.py
Scheduled maintenance, triggered daily by Cloud Scheduler (POST /api/refresh)
or run manually (`python refresh.py`).

Does two things:
  1. Auto-close — recheck every TRACKED job's posting; if it 404s, flag it closed.
     Scoped to tracked jobs because that's the bounded set the user cares about;
     untracked search results self-expire (a closed job stops appearing in scrapes).
  2. Daily digest — re-run the user's last search and email any brand-new matches.
"""

import ssl
import json
import smtplib
import logging
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

import config
from job_store import get_jobs, mark_closed, get_setting, upsert_job
from ranker import parse_keywords, score_jobs
from scraper import is_job_live, search_jobs

log = logging.getLogger("hireview.refresh")


def _auto_close_tracked() -> int:
    """
    Recheck each tracked posting and close the ones that are gone.

    Checked in parallel: serially, a 15s-timeout probe per job meant a pipeline
    of 40 could run past ten minutes and blow the caller's request timeout —
    while the rest of the codebase already fans out its network calls.
    """
    pending = [j for j in get_jobs(status="tracked") if not j.get("closed_at")]
    if not pending:
        return 0

    closed = 0
    with ThreadPoolExecutor(max_workers=min(16, len(pending))) as pool:
        live = pool.map(lambda j: is_job_live(j.get("url", "")), pending)
        for job, still_live in zip(pending, live):
            if still_live is False:  # only an explicit False closes it
                mark_closed(job["id"])
                closed += 1
    return closed


def _digest_new_jobs() -> list[dict]:
    raw = get_setting("last_search")
    if not raw:
        return []
    try:
        p = json.loads(raw)
    except Exception:
        return []

    keywords = p.get("keywords", "")
    jobs = search_jobs(
        keywords=keywords,
        location=p.get("location", ""),
        # Only from env — the UI-entered keys are deliberately never persisted.
        adzuna_app_id=config.ADZUNA_APP_ID,
        adzuna_app_key=config.ADZUNA_APP_KEY,
        use_greenhouse=p.get("use_greenhouse", True),
        use_lever=p.get("use_lever", True),
        use_ashby=p.get("use_ashby", True),
        target_companies=p.get("companies"),
    )

    # Score before persisting, exactly as /api/search does. Skipping this wrote
    # every digest-discovered job with match_score 0, so the same posting sorted
    # differently depending on which path happened to find it first.
    score_jobs(jobs, parse_keywords(keywords), get_setting("resume") or "")

    return [job for job in jobs if upsert_job(job)]  # True == newly inserted


def send_digest_email(jobs: list[dict]) -> None:
    body_lines = [f"{len(jobs)} new job(s) matching your last HireView search:\n"]
    for j in jobs[:50]:
        body_lines.append(
            f"• {j.get('title', '')} — {j.get('company', '')}"
            f" ({j.get('location') or 'location n/a'})\n  {j.get('url', '')}"
        )

    msg = EmailMessage()
    msg["Subject"] = f"HireView: {len(jobs)} new job(s)"
    msg["From"] = config.SMTP_USER
    msg["To"] = config.DIGEST_TO
    msg.set_content("\n".join(body_lines))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx) as s:
        s.login(config.SMTP_USER, config.SMTP_PASS)
        s.send_message(msg)


def run_refresh() -> dict:
    closed = _auto_close_tracked()
    new_jobs = _digest_new_jobs()

    emailed = False
    if new_jobs and config.DIGEST_ENABLED:
        try:
            send_digest_email(new_jobs)
            emailed = True
        except Exception as e:
            log.warning("digest email failed [%s]", e.__class__.__name__)

    summary = {"closed": closed, "new": len(new_jobs), "emailed": emailed}
    log.info("refresh: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=config.LOG_LEVEL)
    print(run_refresh())
