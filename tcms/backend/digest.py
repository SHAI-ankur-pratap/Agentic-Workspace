"""
APScheduler weekly digest email.

Sends a per-project HTML digest to all delivery_head and qa_lead users who
have not opted out.  Scheduled every Monday at 08:00 UTC (Decision 23).

Integration in main.py:
    from digest import start_scheduler, stop_scheduler

    @app.on_event("startup")
    async def _startup():
        start_scheduler()

    @app.on_event("shutdown")
    async def _shutdown():
        stop_scheduler()
"""

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal
from models import ExecutionResult, ExecutionRun, Project, TestCase, User

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# ---------------------------------------------------------------------------
# SMTP configuration (read from environment)
# ---------------------------------------------------------------------------

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "tcms@shorthills.ai")

TCMS_BASE_URL = os.getenv("TCMS_BASE_URL", "https://tcms.shorthills.ai")

# How far back to look for "latest run" data.
RECENT_DAYS = 14
# How far back to look for "new test cases this week".
NEW_TC_DAYS = 7


# ---------------------------------------------------------------------------
# Data-gathering helpers
# ---------------------------------------------------------------------------


def _compute_coverage(run: ExecutionRun) -> float:
    """Return pass% for the given run (0.0 if no results)."""
    results = run.results or []
    if not results:
        return 0.0
    passed = sum(1 for r in results if r.status == "pass")
    return round(passed / len(results) * 100, 1)


def _get_project_digest_data(project: Project, db, now: datetime) -> Optional[dict]:
    """Gather digest statistics for a single project.

    Returns None if the project has no useful data to surface.
    """
    cutoff_14d = now - timedelta(days=RECENT_DAYS)
    cutoff_7d = now - timedelta(days=NEW_TC_DAYS)

    # Latest completed run within the last 14 days.
    latest_run: Optional[ExecutionRun] = (
        db.query(ExecutionRun)
        .filter(
            ExecutionRun.project_id == project.id,
            ExecutionRun.status == "completed",
            ExecutionRun.created_at >= cutoff_14d,
        )
        .order_by(ExecutionRun.created_at.desc())
        .first()
    )

    coverage_pct = _compute_coverage(latest_run) if latest_run else None

    # New test cases added in the last 7 days.
    new_tc_count: int = (
        db.query(TestCase)
        .filter(
            TestCase.project_id == project.id,
            TestCase.created_at >= cutoff_7d,
        )
        .count()
    )

    # Test cases that need re-run:
    # - either they have no result in the latest completed run, or
    # - their last result in the latest completed run is "fail".
    if latest_run:
        run_result_map: dict = {}
        for r in (latest_run.results or []):
            run_result_map[r.test_case_id] = r.status

        all_active_ids = [
            tc.id for tc in
            db.query(TestCase)
            .filter(TestCase.project_id == project.id, TestCase.status == "active")
            .all()
        ]

        needs_rerun = 0
        for tc_id in all_active_ids:
            result_status = run_result_map.get(tc_id)
            if result_status is None or result_status == "fail":
                needs_rerun += 1
    else:
        # No recent run at all — every active test case needs attention.
        needs_rerun = (
            db.query(TestCase)
            .filter(TestCase.project_id == project.id, TestCase.status == "active")
            .count()
        )

    total_active_tcs: int = (
        db.query(TestCase)
        .filter(TestCase.project_id == project.id, TestCase.status == "active")
        .count()
    )

    if total_active_tcs == 0 and new_tc_count == 0:
        return None  # Nothing to report

    return {
        "project": project,
        "latest_run": latest_run,
        "coverage_pct": coverage_pct,
        "new_tc_count": new_tc_count,
        "needs_rerun": needs_rerun,
        "total_active_tcs": total_active_tcs,
    }


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------


def _build_project_row(data: dict, base_url: str) -> str:
    project: Project = data["project"]
    latest_run: Optional[ExecutionRun] = data["latest_run"]
    coverage_pct = data["coverage_pct"]
    new_tc_count = data["new_tc_count"]
    needs_rerun = data["needs_rerun"]
    total_active_tcs = data["total_active_tcs"]

    run_link = (
        f'<a href="{base_url}/projects/{project.id}/runs/{latest_run.id}" '
        f'style="color:#7c6af7;text-decoration:none">{latest_run.name}</a>'
        if latest_run else
        '<span style="color:#aaa">No recent run</span>'
    )

    if coverage_pct is None:
        coverage_cell = '<span style="color:#aaa">—</span>'
    elif coverage_pct >= 80:
        coverage_cell = f'<span style="color:#16a34a;font-weight:600">{coverage_pct}%</span>'
    elif coverage_pct >= 50:
        coverage_cell = f'<span style="color:#ca8a04;font-weight:600">{coverage_pct}%</span>'
    else:
        coverage_cell = f'<span style="color:#dc2626;font-weight:600">{coverage_pct}%</span>'

    new_tc_cell = (
        f'<span style="color:#7c6af7;font-weight:600">+{new_tc_count}</span>'
        if new_tc_count > 0 else
        '<span style="color:#aaa">0</span>'
    )

    needs_rerun_cell = (
        f'<span style="color:#dc2626;font-weight:600">{needs_rerun}</span>'
        if needs_rerun > 0 else
        '<span style="color:#16a34a">0</span>'
    )

    return f"""
    <tr>
      <td style="padding:12px 16px;border-bottom:1px solid #f0f0f0;font-weight:500;color:#1a1a2e">
        <a href="{base_url}/projects/{project.id}"
           style="color:#1a1a2e;text-decoration:none">{project.name}</a>
        {f'<br><span style="font-size:12px;color:#aaa">{project.client_name}</span>' if project.client_name else ''}
      </td>
      <td style="padding:12px 16px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#555">
        {run_link}
      </td>
      <td style="padding:12px 16px;border-bottom:1px solid #f0f0f0;text-align:center;font-family:'IBM Plex Mono',monospace;font-size:14px">
        {coverage_cell}
      </td>
      <td style="padding:12px 16px;border-bottom:1px solid #f0f0f0;text-align:center;font-size:13px">
        {new_tc_cell}
      </td>
      <td style="padding:12px 16px;border-bottom:1px solid #f0f0f0;text-align:center;font-size:13px">
        {needs_rerun_cell}
      </td>
    </tr>"""


def _build_digest_html(
    user: User,
    project_data_list: List[dict],
    base_url: str,
    week_start: str,
) -> str:
    rows = "".join(_build_project_row(d, base_url) for d in project_data_list)
    opt_out_url = f"{base_url}/settings/digest-opt-out"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>TCMS Weekly QA Digest</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'DM Sans',system-ui,sans-serif;color:#1a1a2e">
  <div style="max-width:680px;margin:32px auto;padding:0 16px">

    <!-- Header -->
    <div style="background:#1a1a2e;border-radius:10px 10px 0 0;padding:24px 32px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:18px;font-weight:700;color:#fff">TCMS Weekly Digest</div>
        <div style="font-size:13px;color:#888;margin-top:4px">Week of {week_start}</div>
      </div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#7c6af7;background:#2d2d4a;padding:4px 10px;border-radius:20px">
        Shorthills.ai
      </div>
    </div>

    <!-- Greeting -->
    <div style="background:#fff;padding:24px 32px;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb">
      <p style="font-size:15px;line-height:1.65;color:#555;margin:0">
        Hi {user.full_name.split()[0]},<br><br>
        Here is your weekly QA summary across all active projects.
      </p>
    </div>

    <!-- Table -->
    <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;overflow:hidden">
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#f9fafb">
            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.5px">Project</th>
            <th style="padding:10px 16px;text-align:left;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.5px">Latest Run</th>
            <th style="padding:10px 16px;text-align:center;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.5px">Coverage</th>
            <th style="padding:10px 16px;text-align:center;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.5px">New TCs</th>
            <th style="padding:10px 16px;text-align:center;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.5px">Need Re-run</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>

    <!-- CTA -->
    <div style="background:#fff;padding:24px 32px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 0 0;text-align:center">
      <a href="{base_url}" style="display:inline-block;background:#7c6af7;color:#fff;font-size:14px;font-weight:600;padding:12px 28px;border-radius:8px;text-decoration:none">
        Open TCMS Dashboard →
      </a>
    </div>

    <!-- Footer -->
    <div style="padding:20px 0;text-align:center">
      <p style="font-size:12px;color:#aaa;margin:0">
        You are receiving this because you are a team member on one or more TCMS projects.<br>
        <a href="{opt_out_url}" style="color:#aaa">Unsubscribe from weekly digest</a>
      </p>
    </div>

  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# SMTP sender
# ---------------------------------------------------------------------------


def _send_email(to_address: str, subject: str, html_body: str) -> None:
    """Send a single HTML email via smtplib (STARTTLS on port 587)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_address
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_address], msg.as_string())
            logger.info("Digest email sent to %s", to_address)
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending digest to %s: %s", to_address, exc)
    except OSError as exc:
        logger.error("Network error sending digest to %s: %s", to_address, exc)


# ---------------------------------------------------------------------------
# Main digest job
# ---------------------------------------------------------------------------


async def send_weekly_digest() -> None:
    """Gather project stats and email a digest to every eligible user.

    Runs every Monday at 08:00 UTC (configured in start_scheduler).

    Algorithm:
    1. Load all active projects.
    2. For each project, compute stats (latest completed run in last 14 days,
       coverage %, new TCs this week, TCs needing re-run).
    3. Load all users with role in {delivery_head, qa_lead} who have not
       opted out of the digest.
    4. For each such user, build a personalised HTML email that lists every
       project with reportable data and send it.
    """
    logger.info("Starting weekly digest job at %s", datetime.utcnow().isoformat())
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        week_start = (now - timedelta(days=now.weekday())).strftime("%B %d, %Y")

        active_projects: List[Project] = (
            db.query(Project).filter(Project.status == "active").all()
        )

        # Compute stats for all projects upfront.
        project_data_list: List[dict] = []
        for project in active_projects:
            data = _get_project_digest_data(project, db, now)
            if data:
                project_data_list.append(data)

        if not project_data_list:
            logger.info("No project data to include in digest — skipping email send.")
            return

        # Load recipients.
        recipients: List[User] = (
            db.query(User)
            .filter(
                User.role.in_(["delivery_head", "qa_lead"]),
                User.is_active == True,  # noqa: E712
                User.digest_opt_out == False,  # noqa: E712
            )
            .all()
        )

        if not recipients:
            logger.info("No digest recipients found — skipping.")
            return

        base_url = TCMS_BASE_URL

        for user in recipients:
            subject = f"TCMS Weekly QA Digest — {week_start}"
            try:
                html_body = _build_digest_html(user, project_data_list, base_url, week_start)
                _send_email(user.email, subject, html_body)
            except Exception as exc:
                logger.error(
                    "Failed to build/send digest for user %s (%s): %s",
                    user.id, user.email, exc,
                )

        logger.info(
            "Weekly digest complete: %d project(s), %d recipient(s).",
            len(project_data_list), len(recipients),
        )
    except Exception as exc:
        logger.exception("Unhandled error in weekly digest job: %s", exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------


def start_scheduler() -> None:
    """Register the weekly digest job and start the scheduler.

    Call this from FastAPI's startup event handler.
    """
    scheduler.add_job(
        send_weekly_digest,
        CronTrigger(day_of_week="mon", hour=8, minute=0, timezone="UTC"),
        id="weekly_digest",
        replace_existing=True,
        misfire_grace_time=3600,  # allow up to 1 h late-start tolerance
    )
    scheduler.start()
    logger.info("APScheduler started — weekly digest job registered (Monday 08:00 UTC).")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler.

    Call this from FastAPI's shutdown event handler.
    """
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
