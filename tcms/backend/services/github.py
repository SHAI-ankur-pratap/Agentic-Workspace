"""
GitHub PR integration service.

Called by the webhook router after HMAC signature verification has already been
performed.  All network I/O is done with httpx.AsyncClient so that the FastAPI
event-loop is never blocked.
"""

from __future__ import annotations

import logging
import os
import uuid
from fnmatch import fnmatch
from typing import List, Optional

import httpx
from sqlalchemy.orm import Session

from models import ComponentTagRule, ExecutionResult, ExecutionRun, TestCase

logger = logging.getLogger(__name__)

MAX_PR_FILES = 50  # Decision 24: cap to avoid excessively large runs


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


async def get_pr_changed_files(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
) -> List[str]:
    """Return the list of filenames changed in a pull request (capped at MAX_PR_FILES).

    Uses the GitHub REST endpoint:
        GET /repos/{owner}/{repo}/pulls/{pr_number}/files

    Parameters
    ----------
    owner:      GitHub organisation or user name
    repo:       Repository name (without owner prefix)
    pr_number:  Pull request number
    token:      GitHub personal-access-token (or empty string for unauth requests)

    Returns
    -------
    List of filename strings.  Empty list on any network / API error.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers: dict = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params={"per_page": MAX_PR_FILES})
            resp.raise_for_status()
            files = resp.json()
            return [f["filename"] for f in files[:MAX_PR_FILES]]
    except httpx.HTTPStatusError as exc:
        logger.error(
            "GitHub API returned %s when fetching PR files for %s/%s#%s: %s",
            exc.response.status_code, owner, repo, pr_number, exc,
        )
    except httpx.RequestError as exc:
        logger.error("Network error fetching PR files for %s/%s#%s: %s", owner, repo, pr_number, exc)
    except Exception as exc:
        logger.error("Unexpected error fetching PR files: %s", exc)
    return []


# ---------------------------------------------------------------------------
# File → component tag mapping
# ---------------------------------------------------------------------------


def map_files_to_component_tags(
    files: List[str],
    rules: List[ComponentTagRule],
) -> set[str]:
    """Match each file path against the project's ComponentTagRules using fnmatch.

    A file may match multiple rules, contributing multiple tags.  The returned
    set contains every tag whose corresponding glob pattern matched at least one
    of the changed files.

    Parameters
    ----------
    files:  List of file paths returned by get_pr_changed_files().
    rules:  ComponentTagRule ORM objects for the project.

    Returns
    -------
    Set of component_tag strings (may be empty).
    """
    matched: set[str] = set()
    for file_path in files:
        for rule in rules:
            if fnmatch(file_path, rule.file_pattern):
                matched.add(rule.component_tag)
    return matched


# ---------------------------------------------------------------------------
# Test-case lookup
# ---------------------------------------------------------------------------


def find_affected_test_cases(
    db: Session,
    project_id: str,
    component_tags: set[str],
) -> List[TestCase]:
    """Return active test cases whose component_tags overlap with the given set.

    Because SQLite does not support JSON_CONTAINS we filter in Python after
    loading all active test cases for the project (Decision 22: SQLite-compatible
    approach; acceptable given typical project sizes).

    Parameters
    ----------
    db:             SQLAlchemy session.
    project_id:     UUID string of the owning project.
    component_tags: Set of component tag strings to match against.

    Returns
    -------
    List of matching TestCase ORM objects.
    """
    if not component_tags:
        # No tags identified — return all active cases so nothing regresses.
        return (
            db.query(TestCase)
            .filter(TestCase.project_id == project_id, TestCase.status == "active")
            .all()
        )

    all_active = (
        db.query(TestCase)
        .filter(TestCase.project_id == project_id, TestCase.status == "active")
        .all()
    )
    return [
        tc for tc in all_active
        if component_tags.intersection(set(tc.component_tags or []))
    ]


# ---------------------------------------------------------------------------
# Execution-run creation
# ---------------------------------------------------------------------------


async def create_pr_execution_run(
    db: Session,
    project_id: str,
    pr_number: int,
    test_cases: List[TestCase],
    run_name: str,
) -> ExecutionRun:
    """Create an ExecutionRun (is_live=True) and one pending ExecutionResult per test case.

    Parameters
    ----------
    db:         SQLAlchemy session (caller must commit or this function commits).
    project_id: UUID of the owning project.
    pr_number:  GitHub pull-request number stored on the run for traceability.
    test_cases: List of TestCase objects to include in the run.
    run_name:   Human-readable run name (will be truncated to 255 chars).

    Returns
    -------
    The newly created, committed ExecutionRun instance.
    """
    run_id = str(uuid.uuid4())
    run = ExecutionRun(
        id=run_id,
        project_id=project_id,
        name=run_name[:255],
        status="in_progress",
        is_live=True,
        github_pr_number=pr_number,
    )
    db.add(run)
    db.flush()  # populate run.id without a full commit

    for tc in test_cases:
        db.add(
            ExecutionResult(
                id=str(uuid.uuid4()),
                run_id=run_id,
                test_case_id=tc.id,
                status="pending",
            )
        )

    db.commit()
    db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# GitHub PR comment
# ---------------------------------------------------------------------------


async def post_pr_comment(
    owner: str,
    repo: str,
    pr_number: int,
    token: str,
    run_id: str,
    tc_count: int,
    base_url: str,
    project_id: Optional[str] = None,
) -> None:
    """Post a comment on the pull request linking back to the TCMS execution run.

    Failures are logged but never re-raised so a comment failure can never
    break the webhook response.

    Parameters
    ----------
    owner:      GitHub org/user name.
    repo:       Repository name.
    pr_number:  Pull request number.
    token:      GitHub personal-access-token.
    run_id:     UUID of the newly created ExecutionRun.
    tc_count:   Number of test cases in the run.
    base_url:   Root URL of the TCMS deployment (e.g. https://tcms.shorthills.ai).
    project_id: Optional project UUID used to build the deep-link URL.
    """
    if not token:
        logger.warning("GITHUB_TOKEN not set — skipping PR comment for PR #%s", pr_number)
        return

    if project_id:
        run_url = f"{base_url}/projects/{project_id}/runs/{run_id}"
    else:
        run_url = f"{base_url}/runs/{run_id}"

    api_run_url = (
        f"{base_url}/api/projects/{project_id}/runs/{run_id}"
        if project_id
        else f"{base_url}/api/runs/{run_id}"
    )

    body = (
        f"🧪 **TCMS**: {tc_count} test case(s) affected by this change. "
        f"[View execution run →]({run_url})"
    )

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
            logger.info(
                "Posted PR comment for PR #%s (%s test cases, run %s)", pr_number, tc_count, run_id
            )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "GitHub API returned %s when posting PR comment: %s", exc.response.status_code, exc
        )
    except httpx.RequestError as exc:
        logger.error("Network error posting PR comment: %s", exc)
    except Exception as exc:
        logger.error("Unexpected error posting PR comment: %s", exc)


# ---------------------------------------------------------------------------
# Slack notification
# ---------------------------------------------------------------------------


async def post_slack_notification(
    webhook_url: str,
    project_name: str,
    pr_number: int,
    tc_count: int,
    run_url: str,
) -> None:
    """Send a Slack incoming-webhook notification about the new PR execution run.

    Failures are logged but never re-raised.

    Parameters
    ----------
    webhook_url:  Slack incoming-webhook URL configured on the project.
    project_name: Human-readable project name included in the message.
    pr_number:    Pull request number.
    tc_count:     Number of test cases included in the run.
    run_url:      Deep-link URL to the TCMS run page.
    """
    text = (
        f":test_tube: *TCMS — {project_name}*: "
        f"{tc_count} test case(s) triggered by PR #{pr_number}. "
        f"<{run_url}|View execution run>"
    )
    payload = {"text": text}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            logger.info(
                "Slack notification sent for PR #%s in project '%s'", pr_number, project_name
            )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Slack webhook returned %s: %s", exc.response.status_code, exc
        )
    except httpx.RequestError as exc:
        logger.error("Network error sending Slack notification: %s", exc)
    except Exception as exc:
        logger.error("Unexpected error sending Slack notification: %s", exc)
