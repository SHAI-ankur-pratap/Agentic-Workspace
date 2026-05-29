import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

import llm as llm_module
import pdf as pdf_module
from auth import get_current_user
from database import get_db
from models import ExecutionResult, ExecutionRun, Project, ShareToken, TestCase, User
from schemas import ShareLinkResponse

router = APIRouter(tags=["reports"])
public_router = APIRouter(tags=["public-reports"])

SHARE_TOKEN_TTL_DAYS = 30
EXECUTIVE_SUMMARY_CACHE_TTL_HOURS = 24


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _get_run_or_404(project_id: str, run_id: str, db: Session) -> ExecutionRun:
    run = (
        db.query(ExecutionRun)
        .filter(ExecutionRun.id == run_id, ExecutionRun.project_id == project_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


def _compute_stats(run: ExecutionRun) -> dict:
    results = run.results or []
    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")
    blocked = sum(1 for r in results if r.status == "blocked")
    pending = sum(1 for r in results if r.status == "pending")
    coverage_pct = round((passed / total * 100), 1) if total > 0 else 0.0
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "blocked": blocked,
        "pending": pending,
        "coverage_pct": coverage_pct,
    }


def _priority_label(priority: str) -> str:
    return {"P1": "CRITICAL", "P2": "HIGH", "P3": "MEDIUM", "P4": "LOW"}.get(priority, priority)


def _status_badge_html(status_val: str) -> str:
    styles = {
        "pass": "background:#dcfce7;color:#16a34a",
        "fail": "background:#fee2e2;color:#dc2626",
        "skip": "background:#fef9c3;color:#ca8a04",
        "blocked": "background:#fce7f3;color:#be185d",
        "pending": "background:#f3f4f6;color:#4b5563",
    }
    style = styles.get(status_val, "background:#f3f4f6;color:#4b5563")
    label = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP", "blocked": "BLOCKED", "pending": "PENDING"}.get(
        status_val, status_val.upper()
    )
    return (
        f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;'
        f"font-weight:600;border-radius:20px;padding:2px 8px;{style}\">"
        f"{label}</span>"
    )


def _render_report_html(
    project: Project,
    run: ExecutionRun,
    stats: dict,
    results_with_cases: list,
    executive_summary: Optional[str] = None,
    is_public: bool = False,
    expires_at: Optional[datetime] = None,
) -> str:
    now_str = datetime.utcnow().strftime("%Y-%m-%d")
    expiry_str = expires_at.strftime("%Y-%m-%d") if expires_at else ""

    rows_html = ""
    for result, tc in results_with_cases:
        badge = _status_badge_html(result.status)
        steps_escaped = (tc.steps or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        expected_escaped = (tc.expected_result or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        actual_escaped = (result.actual_result or "—").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        priority_label = _priority_label(tc.priority)

        if is_public:
            row = f"""
            <tr>
              <td style="font-family:'IBM Plex Mono',monospace;color:#7c6af7;white-space:nowrap">{tc.tc_id}</td>
              <td>
                <details>
                  <summary style="cursor:pointer;font-weight:500;color:#1a1a2e">{tc.title}</summary>
                  <div style="margin-top:8px;padding:12px;background:#f9fafb;border-radius:6px;font-size:14px;color:#555">
                    <strong>Steps:</strong><br>{steps_escaped}<br><br>
                    <strong>Expected:</strong><br>{expected_escaped}
                  </div>
                </details>
              </td>
              <td style="white-space:nowrap;color:#555;font-size:13px">{priority_label}</td>
              <td style="text-align:center">{badge}</td>
            </tr>"""
        else:
            row = f"""
            <tr>
              <td style="font-family:'IBM Plex Mono',monospace;color:#7c6af7;white-space:nowrap">{tc.tc_id}</td>
              <td style="font-weight:500;color:#1a1a2e">{tc.title}</td>
              <td style="color:#555;font-size:12px">{steps_escaped}</td>
              <td style="color:#555;font-size:12px">{expected_escaped}</td>
              <td style="color:#555;font-size:12px">{actual_escaped}</td>
              <td style="white-space:nowrap;color:#555;font-size:12px">{priority_label}</td>
              <td style="text-align:center">{badge}</td>
            </tr>"""
        rows_html += row

    executive_card = ""
    if executive_summary:
        executive_card = f"""
        <div style="border-left:4px solid #7c6af7;padding:20px 24px;background:#fff;
                    border-radius:0 10px 10px 0;box-shadow:0 1px 3px rgba(0,0,0,0.06);
                    margin-bottom:32px">
          <p style="font-size:18px;line-height:1.65;color:#111827;margin:0">{executive_summary}</p>
        </div>"""

    if is_public:
        table_header = """
        <tr style="background:#f9fafb">
          <th>ID</th><th>Title</th><th>Priority</th><th>Status</th>
        </tr>"""
        footer_html = f"""
        <footer style="margin-top:48px;padding-top:16px;border-top:1px solid #e5e7eb;
                       text-align:center;font-size:13px;color:#888">
          Generated by TCMS &middot; Shorthills.ai
          {f'&middot; Valid until {expiry_str}' if expiry_str else ''}
        </footer>"""
        header_section = f"""
        <header style="padding:16px 0;border-bottom:1px solid #e5e7eb;margin-bottom:32px;
                       display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:16px;font-weight:700;color:#1a1a2e">Shorthills.ai</span>
          <span style="font-size:14px;color:#888">QA Team</span>
        </header>
        <h1 style="font-size:28px;font-weight:700;color:#1a1a2e;margin:0 0 4px">{project.name}</h1>
        <p style="font-size:14px;color:#888;margin:0 0 32px">
          {project.client_name or ''}{' &middot; ' if project.client_name else ''}{run.name} &middot; {now_str}
        </p>"""
        stats_section = f"""
        <div style="display:flex;gap:0;margin-bottom:40px;text-align:center;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden">
          <div style="flex:1;padding:24px 16px;border-right:1px solid #e5e7eb">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:32px;font-weight:700;color:#16a34a;line-height:1">{stats['passed']}</div>
            <div style="font-size:13px;color:#888;margin-top:6px;text-transform:uppercase;letter-spacing:0.5px">Passed</div>
          </div>
          <div style="flex:1;padding:24px 16px;border-right:1px solid #e5e7eb">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:32px;font-weight:700;color:#dc2626;line-height:1">{stats['failed']}</div>
            <div style="font-size:13px;color:#888;margin-top:6px;text-transform:uppercase;letter-spacing:0.5px">Failed</div>
          </div>
          <div style="flex:1;padding:24px 16px">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:32px;font-weight:700;color:#ca8a04;line-height:1">{stats['skipped']}</div>
            <div style="font-size:13px;color:#888;margin-top:6px;text-transform:uppercase;letter-spacing:0.5px">Skipped</div>
          </div>
        </div>"""
        coverage_bar_pct = min(stats["coverage_pct"], 100)
        bar_color = "#7c6af7" if coverage_bar_pct >= 70 else ("#ca8a04" if coverage_bar_pct >= 40 else "#dc2626")
        coverage_section = f"""
        <div style="margin-bottom:40px">
          <div style="display:flex;justify-content:space-between;margin-bottom:8px">
            <span style="font-size:14px;color:#555;font-weight:500">Coverage</span>
            <span style="font-family:'IBM Plex Mono',monospace;font-size:14px;color:#1a1a2e;font-weight:600">{stats['coverage_pct']}%</span>
          </div>
          <div style="height:6px;background:#e5e5e5;border-radius:3px">
            <div style="height:100%;width:{coverage_bar_pct}%;background:{bar_color};border-radius:3px;transition:width 0.3s ease"></div>
          </div>
        </div>"""
        layout_style = "max-width:800px;margin:0 auto;padding:0 16px;font-family:'DM Sans',system-ui,sans-serif;color:#111827"
    else:
        table_header = """
        <tr style="background:#f9fafb">
          <th>ID</th><th>Title</th><th>Steps</th><th>Expected</th><th>Actual</th><th>Priority</th><th>Status</th>
        </tr>"""
        footer_html = ""
        header_section = f"""
        <div style="background:#1a1a2e;color:#fff;padding:20px 32px;margin:-32px -32px 32px">
          <h1 style="font-size:20px;font-weight:600;margin:0 0 4px">QA Execution Report</h1>
          <p style="font-size:13px;color:#aaa;margin:0">{project.name} &middot; {run.name} &middot; {now_str}</p>
        </div>"""
        stats_section = f"""
        <div style="display:flex;gap:16px;margin-bottom:32px">
          <div style="flex:1;padding:16px 20px;background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);text-align:center">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:24px;font-weight:700;color:#16a34a">{stats['passed']}</div>
            <div style="font-size:12px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px">Passed</div>
          </div>
          <div style="flex:1;padding:16px 20px;background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);text-align:center">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:24px;font-weight:700;color:#dc2626">{stats['failed']}</div>
            <div style="font-size:12px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px">Failed</div>
          </div>
          <div style="flex:1;padding:16px 20px;background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);text-align:center">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:24px;font-weight:700;color:#ca8a04">{stats['skipped']}</div>
            <div style="font-size:12px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px">Skipped</div>
          </div>
          <div style="flex:1;padding:16px 20px;background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);text-align:center">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:24px;font-weight:700;color:#be185d">{stats['blocked']}</div>
            <div style="font-size:12px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px">Blocked</div>
          </div>
          <div style="flex:1;padding:16px 20px;background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);text-align:center">
            <div style="font-family:'IBM Plex Mono',monospace;font-size:24px;font-weight:700;color:#7c6af7">{stats['coverage_pct']}%</div>
            <div style="font-size:12px;color:#888;margin-top:4px;text-transform:uppercase;letter-spacing:0.5px">Coverage</div>
          </div>
        </div>"""
        coverage_section = ""
        layout_style = "max-width:1100px;margin:0 auto;padding:32px;font-family:'DM Sans',system-ui,sans-serif;color:#1a1a2e;background:#f5f5f5;min-height:100vh"

    print_css = """
    @media print {
      details { display: block; }
      details > summary::marker { display: none; }
      details > div { display: block !important; }
      header, footer { break-inside: avoid; }
      tr { break-inside: avoid; }
    }
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QA Report — {project.name}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: {'#ffffff' if is_public else '#f5f5f5'}; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th {{ text-align: left; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #888; font-weight: 600; padding: 10px 12px; }}
    td {{ padding: 12px; font-size: {'14px' if is_public else '13px'}; border-bottom: 1px solid #f0f0f0; vertical-align: top; line-height: 1.5; color: #555; }}
    tr:last-child td {{ border-bottom: none; }}
    details summary::-webkit-details-marker {{ display: none; }}
    {print_css}
  </style>
</head>
<body>
  <div style="{layout_style}">
    {header_section}
    {executive_card}
    {stats_section}
    {coverage_section}
    <div style="background:#fff;border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.06);overflow:hidden">
      <div style="padding:16px 20px;border-bottom:1px solid #e5e5e5">
        <h2 style="font-size:{'15px' if is_public else '14px'};font-weight:600;color:#1a1a2e;margin:0">Test Cases ({stats['total']})</h2>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead>{table_header}</thead>
          <tbody>{rows_html}</tbody>
        </table>
      </div>
    </div>
    {footer_html}
  </div>
</body>
</html>"""
    return html


async def _get_or_generate_executive_summary(
    run: ExecutionRun, project: Project, stats: dict, db: Session
) -> Optional[str]:
    """Return cached summary or generate a fresh one if stale/missing."""
    if run.executive_summary and run.executive_summary_cached_at:
        age = datetime.utcnow() - run.executive_summary_cached_at
        if age.total_seconds() < EXECUTIVE_SUMMARY_CACHE_TTL_HOURS * 3600:
            return run.executive_summary

    try:
        summary = await llm_module.generate_executive_summary(project.name, stats)
        run.executive_summary = summary
        run.executive_summary_cached_at = datetime.utcnow()
        db.commit()
        return summary
    except Exception:
        return run.executive_summary  # return stale summary rather than nothing


def _load_results_with_cases(run: ExecutionRun, db: Session) -> list:
    results = (
        db.query(ExecutionResult)
        .filter(ExecutionResult.run_id == run.id)
        .all()
    )
    pairs = []
    for result in results:
        tc = db.query(TestCase).filter(TestCase.id == result.test_case_id).first()
        if tc:
            pairs.append((result, tc))
    pairs.sort(key=lambda x: x[1].tc_id)
    return pairs


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/api/projects/{project_id}/runs/{run_id}/report.html",
    response_class=HTMLResponse,
)
async def get_report_html(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(project_id, db)
    run = _get_run_or_404(project_id, run_id, db)

    stats = _compute_stats(run)
    results_with_cases = _load_results_with_cases(run, db)
    executive_summary = await _get_or_generate_executive_summary(run, project, stats, db)

    html = _render_report_html(
        project=project,
        run=run,
        stats=stats,
        results_with_cases=results_with_cases,
        executive_summary=executive_summary,
        is_public=False,
    )
    return HTMLResponse(content=html)


@router.get("/api/projects/{project_id}/runs/{run_id}/report.pdf")
async def get_report_pdf(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_project_or_404(project_id, db)
    run = _get_run_or_404(project_id, run_id, db)

    stats = _compute_stats(run)
    results_with_cases = _load_results_with_cases(run, db)
    executive_summary = await _get_or_generate_executive_summary(run, project, stats, db)

    html = _render_report_html(
        project=project,
        run=run,
        stats=stats,
        results_with_cases=results_with_cases,
        executive_summary=executive_summary,
        is_public=False,
    )

    pdf_bytes = await pdf_module.render_pdf(html)
    if pdf_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF rendering is currently unavailable. Please download the HTML report instead.",
        )

    filename = f"report-{run_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/api/projects/{project_id}/runs/{run_id}/share",
    response_model=ShareLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_share_link(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    _get_run_or_404(project_id, run_id, db)

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=SHARE_TOKEN_TTL_DAYS)

    share_token = ShareToken(
        id=str(uuid.uuid4()),
        run_id=run_id,
        token=raw_token,
        expires_at=expires_at,
    )
    db.add(share_token)
    db.commit()

    base_url = "https://tcms.shorthills.ai"  # overridable via env in production
    import os
    base_url = os.getenv("TCMS_BASE_URL", base_url)

    return ShareLinkResponse(
        token=raw_token,
        url=f"{base_url}/reports/{raw_token}",
        expires_at=expires_at,
    )


@public_router.get("/reports/{token}", response_class=HTMLResponse)
async def view_public_report(token: str, db: Session = Depends(get_db)):
    share_token = (
        db.query(ShareToken).filter(ShareToken.token == token).first()
    )

    if not share_token:
        html = _error_page(
            code=404,
            title="Report Not Found",
            message="This report link does not exist. Please check the URL or contact your QA team.",
        )
        return HTMLResponse(content=html, status_code=404)

    if datetime.utcnow() > share_token.expires_at:
        html = _error_page(
            code=410,
            title="Report Link Expired",
            message="This report link has expired. Please contact your QA team to generate a new link.",
            extra=f"This link expired on {share_token.expires_at.strftime('%Y-%m-%d')}.",
        )
        return HTMLResponse(content=html, status_code=410)

    run = db.query(ExecutionRun).filter(ExecutionRun.id == share_token.run_id).first()
    if not run:
        html = _error_page(
            code=404,
            title="Report Not Found",
            message="The run associated with this link no longer exists.",
        )
        return HTMLResponse(content=html, status_code=404)

    project = db.query(Project).filter(Project.id == run.project_id).first()
    if not project:
        html = _error_page(
            code=404,
            title="Project Not Found",
            message="The project associated with this run no longer exists.",
        )
        return HTMLResponse(content=html, status_code=404)

    # For live runs, data is always fresh from DB (no separate snapshot needed since
    # we query live. For non-live runs this is the same query but the data is stable.)
    stats = _compute_stats(run)
    results_with_cases = _load_results_with_cases(run, db)

    # Executive summary: try to generate/use cached
    executive_summary: Optional[str] = None
    if run.executive_summary and run.executive_summary_cached_at:
        age = datetime.utcnow() - run.executive_summary_cached_at
        if age.total_seconds() < EXECUTIVE_SUMMARY_CACHE_TTL_HOURS * 3600:
            executive_summary = run.executive_summary

    try:
        if not executive_summary:
            executive_summary = await llm_module.generate_executive_summary(project.name, stats)
            run.executive_summary = executive_summary
            run.executive_summary_cached_at = datetime.utcnow()
            db.commit()
    except Exception:
        executive_summary = run.executive_summary  # use stale if available

    html = _render_report_html(
        project=project,
        run=run,
        stats=stats,
        results_with_cases=results_with_cases,
        executive_summary=executive_summary,
        is_public=True,
        expires_at=share_token.expires_at,
    )
    return HTMLResponse(content=html)


def _error_page(code: int, title: str, message: str, extra: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — TCMS</title>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'DM Sans', system-ui, sans-serif; background: #f5f5f5; min-height: 100vh;
           display: flex; align-items: center; justify-content: center; color: #1a1a2e; }}
  </style>
</head>
<body>
  <div style="max-width:480px;width:100%;margin:0 auto;padding:16px;text-align:center">
    <div style="background:#fff;border-radius:10px;padding:48px 40px;box-shadow:0 1px 3px rgba(0,0,0,0.06)">
      <div style="font-size:48px;font-weight:700;color:#e5e5e5;margin-bottom:16px">{code}</div>
      <h1 style="font-size:20px;font-weight:600;color:#1a1a2e;margin-bottom:12px">{title}</h1>
      <p style="font-size:15px;line-height:1.65;color:#555;margin-bottom:{'16px' if extra else '0'}">{message}</p>
      {f'<p style="font-size:13px;color:#888">{extra}</p>' if extra else ''}
      <div style="margin-top:32px;padding-top:24px;border-top:1px solid #e5e5e5">
        <span style="font-size:13px;color:#888">Shorthills.ai &middot; QA Team</span>
      </div>
    </div>
  </div>
</body>
</html>"""
