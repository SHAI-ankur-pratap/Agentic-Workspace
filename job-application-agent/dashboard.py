import os
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect
from core.db import JobDatabase

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "applied_jobs.json")
FOLLOWUP_DAYS = 7

MANUAL_STATUSES = {"skipped_account_wall", "skipped_hard_stop", "failed"}


def _parse_dt(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except Exception:
        return None


@app.route("/")
def index():
    db = JobDatabase(DB_PATH)
    jobs = db.get_all()
    now = datetime.now()
    cutoff = now - timedelta(days=FOLLOWUP_DAYS)

    applied, followups, manual, skipped = [], [], [], []

    for job_id, job in jobs.items():
        job["id"] = job_id
        status = job.get("status", "").lower()
        applied_at = _parse_dt(job.get("applied_at", ""))
        job["days_ago"] = (now - applied_at).days if applied_at else None

        if status == "applied":
            applied.append(job)
            is_old = applied_at and applied_at < cutoff
            if is_old or job.get("pinned"):
                followups.append(job)
        elif status in MANUAL_STATUSES:
            manual.append(job)
        elif status == "skipped_low_score":
            skipped.append(job)

    def sort_key(j):
        dt = _parse_dt(j.get("applied_at", ""))
        return dt or datetime.min

    applied.sort(key=sort_key, reverse=True)
    followups.sort(key=sort_key, reverse=True)
    recent = sorted(jobs.values(), key=sort_key, reverse=True)[:5]

    total = len(jobs)
    n_applied = len(applied)
    stats = {
        "applied": n_applied,
        "followup": len(followups),
        "manual": len(manual),
        "skipped": len(skipped),
        "failed": sum(1 for j in jobs.values() if j.get("status", "").lower() == "failed"),
        "total": total,
        "rate": round(n_applied / total * 100) if total else 0,
    }

    last_modified = None
    if os.path.exists(DB_PATH):
        ts = os.path.getmtime(DB_PATH)
        last_modified = datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M")

    return render_template(
        "dashboard.html",
        stats=stats,
        applied=applied,
        followups=followups,
        manual=manual,
        skipped=skipped,
        recent=recent,
        last_modified=last_modified,
    )


@app.route("/pin/<job_id>", methods=["POST"])
def pin(job_id):
    db = JobDatabase(DB_PATH)
    db.toggle_pin(job_id, True)
    return redirect("/#tab-followup")


@app.route("/unpin/<job_id>", methods=["POST"])
def unpin(job_id):
    db = JobDatabase(DB_PATH)
    db.toggle_pin(job_id, False)
    return redirect("/#tab-applied")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, port=port)
