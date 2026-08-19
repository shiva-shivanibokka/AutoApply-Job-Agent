from conftest import make_job

import job_store as js


def test_insert_then_update_reports_new():
    assert js.upsert_job(make_job("a")) is True   # first time
    assert js.upsert_job(make_job("a")) is False  # already seen


def test_status_and_scraped_at_preserved_on_rescrape():
    js.upsert_job(make_job("a"))
    first_seen = js.get_job("a")["scraped_at"]
    js.update_job_status("a", "applied")

    js.upsert_job(make_job("a", title="Senior ML Engineer"))
    row = js.get_job("a")
    assert row["status"] == "applied"          # user status survives re-scrape
    assert row["scraped_at"] == first_seen      # first-seen time never overwritten
    assert row["title"] == "Senior ML Engineer"  # content does update


def test_status_update_sets_timestamp():
    js.upsert_job(make_job("a"))
    js.update_job_status("a", "interviewing")
    row = js.get_job("a")
    assert row["status"] == "interviewing"
    assert row["status_updated_at"]


def test_tracked_filter_excludes_new_and_dismissed():
    for jid, st in [("a", "applied"), ("b", "saved"), ("c", "new"), ("d", "dismissed")]:
        js.upsert_job(make_job(jid))
        if st != "new":
            js.update_job_status(jid, st)
    ids = {j["id"] for j in js.get_jobs(status="tracked")}
    assert ids == {"a", "b"}


def test_required_skills_roundtrip_as_list():
    js.upsert_job(make_job("a", required_skills=["go", "rust"]))
    assert js.get_job("a")["required_skills"] == ["go", "rust"]


def test_settings_upsert():
    assert js.get_setting("resume") is None
    js.set_setting("resume", "hello")
    assert js.get_setting("resume") == "hello"
    js.set_setting("resume", "world")  # conflict -> update
    assert js.get_setting("resume") == "world"


def test_mark_closed_is_idempotent():
    js.upsert_job(make_job("a"))
    js.mark_closed("a")
    ts = js.get_job("a")["closed_at"]
    assert ts
    js.mark_closed("a")  # must not overwrite the original close time
    assert js.get_job("a")["closed_at"] == ts
