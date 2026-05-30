"""
FastMCP server exposing TCMS functionality as MCP tools.

Mounted at /mcp via HTTP SSE transport on the FastAPI app:

    app.mount("/mcp", mcp.get_asgi_app())   # called from main.py

All tools accept an `api_key` parameter and authenticate against the database
before performing any work.  The MCP server manages its own DB sessions
independently of FastAPI's Depends() injection system.
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastmcp import FastMCP
from sqlalchemy.orm import Session

import llm as llm_module
from auth import hash_api_key
from database import SessionLocal
from models import (
    APIKey,
    ExecutionResult,
    ExecutionRun,
    Project,
    ShareToken,
    TCIDSequence,
    TestCase,
    User,
)

logger = logging.getLogger(__name__)

mcp = FastMCP("TCMS")

SHARE_TOKEN_TTL_DAYS = 30

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_db() -> Session:
    """Return a new SQLAlchemy session.  Caller is responsible for closing it."""
    return SessionLocal()


def _authenticate(api_key: str, db: Session) -> Optional[User]:
    """Validate an API key and return the owning user, or None if invalid."""
    key_hash = hash_api_key(api_key)
    api_key_obj = db.query(APIKey).filter(APIKey.key_hash == key_hash).first()
    if not api_key_obj:
        return None
    return db.query(User).filter(
        User.id == api_key_obj.user_id, User.is_active == True  # noqa: E712
    ).first()


def _require_auth(api_key: str, db: Session) -> User:
    """Raise ValueError if the API key is invalid (FastMCP surfaces as tool error)."""
    user = _authenticate(api_key, db)
    if not user:
        raise ValueError("Invalid or revoked API key.")
    return user


def _next_tc_id(project_id: str, db: Session) -> str:
    """Atomically increment the per-project sequence and return the next TC-ID string."""
    seq = db.query(TCIDSequence).filter(TCIDSequence.project_id == project_id).with_for_update().first()
    if seq is None:
        seq = TCIDSequence(project_id=project_id, next_seq=1)
        db.add(seq)
        db.flush()

    tc_id = f"TC-{seq.next_seq:04d}"
    seq.next_seq += 1
    db.flush()
    return tc_id


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def tcms_list_projects(api_key: str) -> dict:
    """List all projects accessible to the authenticated user.

    Returns
    -------
    {"projects": [{id, name, client_name, status}, ...]}
    """
    db = _get_db()
    try:
        _require_auth(api_key, db)
        projects = db.query(Project).order_by(Project.created_at.desc()).all()
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "client_name": p.client_name,
                    "status": p.status,
                }
                for p in projects
            ]
        }
    finally:
        db.close()


@mcp.tool()
async def tcms_get_test_cases(
    api_key: str,
    project_id: str,
    status: str = "active",
) -> dict:
    """Retrieve test cases for a project, optionally filtered by status.

    Parameters
    ----------
    api_key:    TCMS API key for authentication.
    project_id: UUID of the project.
    status:     Filter by TC status — "active" (default), "draft", "deprecated", or "all".

    Returns
    -------
    {"test_cases": [{tc_id, title, steps, expected_result, priority, component_tags}, ...]}
    """
    db = _get_db()
    try:
        _require_auth(api_key, db)

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        query = db.query(TestCase).filter(TestCase.project_id == project_id)
        if status != "all":
            query = query.filter(TestCase.status == status)
        test_cases = query.order_by(TestCase.tc_id).all()

        return {
            "test_cases": [
                {
                    "tc_id": tc.tc_id,
                    "title": tc.title,
                    "steps": tc.steps,
                    "expected_result": tc.expected_result,
                    "priority": tc.priority,
                    "component_tags": tc.component_tags or [],
                }
                for tc in test_cases
            ]
        }
    finally:
        db.close()


@mcp.tool()
async def tcms_create_test_cases(
    api_key: str,
    project_id: str,
    test_cases: List[dict],
) -> dict:
    """Create one or more test cases in the given project.

    Each item in `test_cases` must contain:
      - title (str)
      - steps (str)
      - expected_result (str)
      - priority (str): "P1", "P2", "P3", or "P4"
      - component_tags (list[str], optional)

    TC-IDs are assigned automatically using the per-project TCIDSequence.

    Returns
    -------
    {"created": N, "tc_ids": ["TC-0001", ...]}
    """
    db = _get_db()
    try:
        user = _require_auth(api_key, db)

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        if not test_cases:
            raise ValueError("test_cases list must not be empty.")

        valid_priorities = {"P1", "P2", "P3", "P4"}
        created_ids: List[str] = []

        for item in test_cases:
            title = str(item.get("title", "")).strip()
            steps = str(item.get("steps", "")).strip()
            expected_result = str(item.get("expected_result", "")).strip()
            priority = str(item.get("priority", "P2")).strip().upper()
            component_tags = item.get("component_tags", []) or []

            if not title:
                raise ValueError("Each test case must have a non-empty 'title'.")
            if not steps:
                raise ValueError(f"Test case '{title}' must have non-empty 'steps'.")
            if not expected_result:
                raise ValueError(f"Test case '{title}' must have a non-empty 'expected_result'.")
            if priority not in valid_priorities:
                priority = "P2"

            tc_id = _next_tc_id(project_id, db)
            tc = TestCase(
                id=str(uuid.uuid4()),
                project_id=project_id,
                tc_id=tc_id,
                title=title,
                steps=steps,
                expected_result=expected_result,
                priority=priority,
                status="active",
                component_tags=list(component_tags),
                is_ai_generated=False,
                created_by=user.id,
            )
            db.add(tc)
            created_ids.append(tc_id)

        db.commit()
        return {"created": len(created_ids), "tc_ids": created_ids}
    finally:
        db.close()


@mcp.tool()
async def tcms_generate_test_cases(
    api_key: str,
    project_id: str,
    user_story: str,
    count: int = 10,
) -> dict:
    """Use the LLM to generate suggested test cases for a user story.

    Generated test cases are NOT saved to the database — they are returned
    for review.  Use tcms_create_test_cases to persist them.

    Parameters
    ----------
    api_key:     TCMS API key.
    project_id:  UUID of the target project (validated but not used for generation).
    user_story:  Natural-language user story or feature description.
    count:       Number of test cases to generate (default 10, max 25).

    Returns
    -------
    {"test_cases": [{title, steps, expected_result, priority}, ...]}
    """
    db = _get_db()
    try:
        _require_auth(api_key, db)

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        if not user_story or not user_story.strip():
            raise ValueError("user_story must be a non-empty string.")

        count = max(1, min(count, 25))  # clamp 1–25

        test_cases = await llm_module.generate_test_cases(user_story, count)
        return {"test_cases": test_cases}
    finally:
        db.close()


@mcp.tool()
async def tcms_create_execution_run(
    api_key: str,
    project_id: str,
    name: str,
    test_case_ids: Optional[List[str]] = None,
) -> dict:
    """Create a new execution run for a project.

    Parameters
    ----------
    api_key:        TCMS API key.
    project_id:     UUID of the project.
    name:           Human-readable name for the run.
    test_case_ids:  Optional list of TestCase UUIDs (not TC-IDs) to include.
                    When omitted all active test cases in the project are included.

    Returns
    -------
    {"run_id": "...", "total_cases": N}
    """
    db = _get_db()
    try:
        user = _require_auth(api_key, db)

        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError(f"Project '{project_id}' not found.")

        if not name or not name.strip():
            raise ValueError("Run name must be a non-empty string.")

        # Resolve test cases
        if test_case_ids:
            test_cases = (
                db.query(TestCase)
                .filter(
                    TestCase.project_id == project_id,
                    TestCase.id.in_(test_case_ids),
                    TestCase.status == "active",
                )
                .all()
            )
            if not test_cases:
                raise ValueError(
                    "None of the specified test_case_ids were found or are active in this project."
                )
        else:
            test_cases = (
                db.query(TestCase)
                .filter(TestCase.project_id == project_id, TestCase.status == "active")
                .all()
            )

        if not test_cases:
            raise ValueError("No active test cases available for this project.")

        run_id = str(uuid.uuid4())
        run = ExecutionRun(
            id=run_id,
            project_id=project_id,
            name=name.strip()[:255],
            status="in_progress",
            is_live=False,
            created_by=user.id,
        )
        db.add(run)
        db.flush()

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
        return {"run_id": run_id, "total_cases": len(test_cases)}
    finally:
        db.close()


@mcp.tool()
async def tcms_record_result(
    api_key: str,
    run_id: str,
    test_case_id: str,
    status: str,
    notes: str = "",
) -> dict:
    """Record or update the result of a single test case within an execution run.

    Parameters
    ----------
    api_key:       TCMS API key.
    run_id:        UUID of the ExecutionRun.
    test_case_id:  UUID of the TestCase (not the TC-ID string like "TC-0001").
    status:        One of: "pass", "fail", "skip", "blocked", "pending".
    notes:         Optional freetext notes / actual result description.

    Returns
    -------
    {"ok": true}
    """
    valid_statuses = {"pass", "fail", "skip", "blocked", "pending"}
    db = _get_db()
    try:
        _require_auth(api_key, db)

        if status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {', '.join(sorted(valid_statuses))}."
            )

        run = db.query(ExecutionRun).filter(ExecutionRun.id == run_id).first()
        if not run:
            raise ValueError(f"Execution run '{run_id}' not found.")

        if run.status in ("completed", "abandoned"):
            raise ValueError(
                f"Cannot record results on a {run.status} run."
            )

        result = (
            db.query(ExecutionResult)
            .filter(
                ExecutionResult.run_id == run_id,
                ExecutionResult.test_case_id == test_case_id,
            )
            .first()
        )
        if not result:
            raise ValueError(
                f"No result found for test case '{test_case_id}' in run '{run_id}'."
            )

        result.status = status
        if notes:
            result.notes = notes
        result.updated_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        db.commit()

        return {"ok": True}
    finally:
        db.close()


@mcp.tool()
async def tcms_get_report_url(api_key: str, run_id: str) -> dict:
    """Get (or create) a public share link for an execution run's HTML report.

    If a non-expired share token already exists it is reused; otherwise a new
    30-day token is created.

    Parameters
    ----------
    api_key:  TCMS API key.
    run_id:   UUID of the ExecutionRun.

    Returns
    -------
    {"url": "https://...", "expires_at": "2026-06-28T08:00:00"}
    """
    db = _get_db()
    try:
        _require_auth(api_key, db)

        run = db.query(ExecutionRun).filter(ExecutionRun.id == run_id).first()
        if not run:
            raise ValueError(f"Execution run '{run_id}' not found.")

        base_url = os.getenv("TCMS_BASE_URL", "https://tcms.shorthills.ai")

        # Reuse an existing, non-expired share token if one exists.
        now = datetime.utcnow()
        existing_token = (
            db.query(ShareToken)
            .filter(ShareToken.run_id == run_id, ShareToken.expires_at > now)
            .order_by(ShareToken.expires_at.desc())
            .first()
        )
        if existing_token:
            return {
                "url": f"{base_url}/reports/{existing_token.token}",
                "expires_at": existing_token.expires_at.isoformat(),
            }

        # Create a new share token.
        raw_token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(days=SHARE_TOKEN_TTL_DAYS)
        share_token = ShareToken(
            id=str(uuid.uuid4()),
            run_id=run_id,
            token=raw_token,
            expires_at=expires_at,
        )
        db.add(share_token)
        db.commit()

        return {
            "url": f"{base_url}/reports/{raw_token}",
            "expires_at": expires_at.isoformat(),
        }
    finally:
        db.close()
