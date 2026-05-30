import os
import sys
import subprocess
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from flask import Flask, render_template, redirect, request, flash
from core.db import JobDatabase

app = Flask(__name__)
app.secret_key = "jobagent-dashboard-secret"

DB_PATH = os.path.join(os.path.dirname(__file__), "applied_jobs.json")
PROFILE_PATH = os.path.join(os.path.dirname(__file__), "profile.yaml")
FOLLOWUP_DAYS = 7
MANUAL_STATUSES = {"skipped_account_wall", "skipped_hard_stop", "failed"}


def _parse_dt(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except Exception:
        return None


def _fallback_url(job):
    """Generate a search URL for old records that have no stored URL."""
    url = job.get("url", "")
    if url:
        return url
    title = quote_plus(job.get("title", ""))
    platform = job.get("platform", "")
    if platform == "linkedin":
        return f"https://www.linkedin.com/jobs/search/?keywords={title}&f_AL=true&sortBy=DD"
    if platform == "naukri":
        slug = job.get("title", "").lower().replace(" ", "-")
        return f"https://www.naukri.com/{slug}-jobs?k={title}&sort=r"
    return ""


def _enrich(jobs):
    now = datetime.now()
    cutoff = now - timedelta(days=FOLLOWUP_DAYS)
    applied, followups, manual, skipped = [], [], [], []
    linkedin_jobs, naukri_jobs = [], []

    for job_id, job in jobs.items():
        job["id"] = job_id
        job["link"] = _fallback_url(job)
        job["link_is_direct"] = bool(job.get("url", ""))
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

        platform = job.get("platform", "")
        if platform == "linkedin":
            linkedin_jobs.append(job)
        elif platform == "naukri":
            naukri_jobs.append(job)

    def sort_key(j):
        dt = _parse_dt(j.get("applied_at", ""))
        return dt or datetime.min

    for lst in (applied, followups, linkedin_jobs, naukri_jobs):
        lst.sort(key=sort_key, reverse=True)

    recent = sorted(jobs.values(), key=sort_key, reverse=True)[:5]
    for j in recent:
        if "link" not in j:
            j["link"] = _fallback_url(j)

    return applied, followups, manual, skipped, linkedin_jobs, naukri_jobs, recent


@app.route("/")
def index():
    db = JobDatabase(DB_PATH)
    jobs = db.get_all()
    applied, followups, manual, skipped, linkedin_jobs, naukri_jobs, recent = _enrich(jobs)

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
        "linkedin": sum(1 for j in jobs.values() if j.get("platform") == "linkedin"),
        "naukri": sum(1 for j in jobs.values() if j.get("platform") == "naukri"),
    }

    last_modified = None
    if os.path.exists(DB_PATH):
        ts = os.path.getmtime(DB_PATH)
        last_modified = datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M")

    started = request.args.get("started")
    platform_started = request.args.get("platform", "")

    return render_template(
        "dashboard.html",
        stats=stats,
        applied=applied,
        followups=followups,
        manual=manual,
        skipped=skipped,
        linkedin_jobs=linkedin_jobs,
        naukri_jobs=naukri_jobs,
        recent=recent,
        last_modified=last_modified,
        started=started,
        platform_started=platform_started,
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


@app.route("/run/<platform>", methods=["POST"])
def run_agent(platform):
    if platform not in ("linkedin", "naukri", "both"):
        return redirect("/")
    cwd = os.path.dirname(os.path.abspath(__file__))
    if platform == "both":
        for p in ("linkedin", "naukri"):
            subprocess.Popen(
                [sys.executable, "main.py", "--platform", p, "--autonomous", "--profile", "profile.yaml"],
                cwd=cwd,
            )
    else:
        subprocess.Popen(
            [sys.executable, "main.py", "--platform", platform, "--autonomous", "--profile", "profile.yaml"],
            cwd=cwd,
        )
    return redirect(f"/?started=1&platform={platform}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(debug=True, port=port)
