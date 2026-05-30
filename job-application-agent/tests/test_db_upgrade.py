import json
import pytest
from pathlib import Path


def make_db(tmp_path):
    from core.db import JobDatabase
    return JobDatabase(db_file=str(tmp_path / "jobs.json"))


def test_mark_processed_stores_new_fields(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed(
        "abc123", "linkedin", "applied",
        title="QA Lead", company="Infosys",
        url="https://linkedin.com/jobs/view/123",
        score=9,
    )
    data = json.loads((tmp_path / "jobs.json").read_text())
    record = data["abc123"]
    assert record["url"] == "https://linkedin.com/jobs/view/123"
    assert record["score"] == 9
    assert record["pinned"] is False
    assert "applied_at" in record and len(record["applied_at"]) > 0


def test_get_all_fills_missing_fields(tmp_path):
    db_file = tmp_path / "jobs.json"
    db_file.write_text(json.dumps({
        "old123": {"platform": "naukri", "status": "Applied", "title": "QA Lead", "company": ""}
    }))
    from core.db import JobDatabase
    db = JobDatabase(db_file=str(db_file))
    all_jobs = db.get_all()
    record = all_jobs["old123"]
    assert record["url"] == ""
    assert record["applied_at"] == ""
    assert record["score"] is None
    assert record["pinned"] is False


def test_toggle_pin_sets_true(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    db.toggle_pin("job1", True)
    all_jobs = db.get_all()
    assert all_jobs["job1"]["pinned"] is True


def test_toggle_pin_sets_false(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    db.toggle_pin("job1", True)
    db.toggle_pin("job1", False)
    all_jobs = db.get_all()
    assert all_jobs["job1"]["pinned"] is False


def test_pin_preserved_on_re_mark(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    db.toggle_pin("job1", True)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    all_jobs = db.get_all()
    assert all_jobs["job1"]["pinned"] is True


def test_toggle_pin_unknown_job_returns_false(tmp_path):
    db = make_db(tmp_path)
    result = db.toggle_pin("nonexistent", True)
    assert result is False
