import hashlib
import hmac
import json
import logging
import os
import uuid
from fnmatch import fnmatch
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from database import get_db
from models import ComponentTagRule, ExecutionResult, ExecutionRun, Project, TestCase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

MAX_PR_FILES = 50  # Decision 24: cap at 50 files to avoid excessively large runs


def _verify_github_signature(payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    """Return True if the X-Hub-Signature-256 header matches the HMAC of the payload."""
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("GITHUB_WEBHOOK_SECRET is not set — rejecting all webhook requests")
        return False
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False

    expected_sig = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, signature_header)


async def _get_pr_files(owner: str, repo: str, pr_number: int) -> List[str]:
    """Fetch the list of changed file paths from the GitHub API."""
    token = os.getenv("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    params = {"per_page": MAX_PR_FILES}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            files = resp.json()
            return [f["filename"] for f in files[:MAX_PR_FILES]]
    except Exception as exc:
        logger.error("Failed to fetch PR files from GitHub: %s", exc)
        return []


def _map_files_to_tags(file_paths: List[str], rules: List[ComponentTagRule]) -> set:
    """Map file paths to component tags using glob pattern matching."""
    matched_tags: set = set()
    for file_path in file_paths:
        for rule in rules:
            if fnmatch(file_path, rule.file_pattern):
                matched_tags.add(rule.component_tag)
    return matched_tags


async def _post_github_comment(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
) -> None:
    token = os.getenv("GITHUB_TOKEN", "")
    if not token:
        logger.warning("GITHUB_TOKEN not set — skipping PR comment")
        return

    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"body": body}, headers=headers)
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Failed to post PR comment: %s", exc)


async def _post_slack_notification(webhook_url: str, message: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json={"text": message})
            resp.raise_for_status()
    except Exception as exc:
        logger.error("Failed to send Slack notification: %s", exc)


@router.post("/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Process GitHub webhook events. Only handles pull_request events
    with action in [opened, synchronize, reopened].
    """
    payload_bytes = await request.body()

    # Verify HMAC signature
    signature_header = request.headers.get("X-Hub-Signature-256")
    if not _verify_github_signature(payload_bytes, signature_header):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing webhook signature",
        )

    # Parse event type
    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "pull_request":
        # Not a PR event — acknowledge and no-op
        return {"status": "ignored", "reason": f"event type '{event_type}' not handled"}

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    pr = payload.get("pull_request", {})
    repository = payload.get("repository", {})
    pr_number = payload.get("number")

    repo_full_name = repository.get("full_name", "")  # e.g. "owner/repo"
    if not repo_full_name or pr_number is None:
        return {"status": "ignored", "reason": "missing repository or PR number"}

    # Find the project by matching github_repo field
    project = (
        db.query(Project)
        .filter(Project.github_repo == repo_full_name, Project.status == "active")
        .first()
    )
    if not project:
        logger.info("No project found for repo '%s' — ignoring webhook", repo_full_name)
        return {"status": "ok", "message": "no project matched"}

    # Parse owner/repo for API calls
    parts = repo_full_name.split("/", 1)
    owner, repo = (parts[0], parts[1]) if len(parts) == 2 else (repo_full_name, "")

    # Fetch changed files (capped at MAX_PR_FILES)
    changed_files = await _get_pr_files(owner, repo, pr_number)

    # Map files to component tags via project's rules
    rules = (
        db.query(ComponentTagRule)
        .filter(ComponentTagRule.project_id == project.id)
        .all()
    )
    matched_tags = _map_files_to_tags(changed_files, rules)

    # Find active test cases matching any of the identified component tags
    if matched_tags:
        all_active_cases = (
            db.query(TestCase)
            .filter(TestCase.project_id == project.id, TestCase.status == "active")
            .all()
        )
        affected_cases = [
            tc for tc in all_active_cases
            if any(tag in (tc.component_tags or []) for tag in matched_tags)
        ]
    else:
        # No rules matched; run all active test cases to ensure nothing regresses
        affected_cases = (
            db.query(TestCase)
            .filter(TestCase.project_id == project.id, TestCase.status == "active")
            .all()
        )

    if not affected_cases:
        logger.info("No test cases affected for PR #%s in project '%s'", pr_number, project.name)
        return {"status": "ok", "message": "no affected test cases", "run_id": None}

    # Create an ExecutionRun for this PR
    pr_title = pr.get("title", f"PR #{pr_number}")
    run_name = f"PR #{pr_number}: {pr_title}"[:255]

    run_id = str(uuid.uuid4())
    run = ExecutionRun(
        id=run_id,
        project_id=project.id,
        name=run_name,
        status="in_progress",
        is_live=True,
        github_pr_number=pr_number,
    )
    db.add(run)
    db.flush()

    for tc in affected_cases:
        db.add(
            ExecutionResult(
                id=str(uuid.uuid4()),
                run_id=run_id,
                test_case_id=tc.id,
                status="pending",
            )
        )

    db.commit()

    # Determine the run URL
    base_url = os.getenv("TCMS_BASE_URL", "https://tcms.shorthills.ai")
    run_url = f"{base_url}/projects/{project.id}/runs/{run_id}"

    # Post a PR comment
    comment_body = (
        f"## TCMS QA Run Created\n\n"
        f"**{len(affected_cases)} test case(s)** are affected by this PR "
        f"({len(changed_files)} file(s) changed"
        + (f", {len(matched_tags)} component tag(s) matched" if matched_tags else "")
        + f").\n\n"
        f"Track progress: {run_url}"
    )
    await _post_github_comment(owner, repo, pr_number, comment_body)

    # Post Slack notification if configured
    if project.slack_webhook_url:
        slack_message = (
            f":test_tube: *TCMS:* {len(affected_cases)} test case(s) triggered by "
            f"PR #{pr_number} in *{project.name}*. "
            f"<{run_url}|View run>"
        )
        await _post_slack_notification(project.slack_webhook_url, slack_message)

    return {
        "status": "ok",
        "run_id": run_id,
        "affected_test_cases": len(affected_cases),
        "matched_tags": list(matched_tags),
        "run_url": run_url,
    }
