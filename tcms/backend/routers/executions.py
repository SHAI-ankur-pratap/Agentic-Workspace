import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import ExecutionResult, ExecutionRun, Project, TestCase, User
from schemas import (
    ExecutionResultResponse,
    ExecutionResultUpdate,
    ExecutionRunCreate,
    ExecutionRunResponse,
    RunSummary,
)

router = APIRouter(prefix="/api/projects/{project_id}/runs", tags=["executions"])

VALID_RESULT_STATUSES = {"pass", "fail", "skip", "blocked", "pending"}


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


def _build_run_summary(run: ExecutionRun) -> RunSummary:
    results = run.results or []
    total = len(results)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    skipped = sum(1 for r in results if r.status == "skip")
    blocked = sum(1 for r in results if r.status == "blocked")
    pending = sum(1 for r in results if r.status == "pending")
    coverage_pct = round((passed / total * 100), 2) if total > 0 else 0.0

    return RunSummary(
        run=ExecutionRunResponse.model_validate(run),
        total=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        blocked=blocked,
        pending=pending,
        coverage_pct=coverage_pct,
        results=[ExecutionResultResponse.model_validate(r) for r in results],
    )


@router.post("", response_model=RunSummary, status_code=status.HTTP_201_CREATED)
def create_run(
    project_id: str,
    payload: ExecutionRunCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    run_id = str(uuid.uuid4())
    run = ExecutionRun(
        id=run_id,
        project_id=project_id,
        name=payload.name,
        status="in_progress",
        is_live=False,
        created_by=current_user.id,
    )
    db.add(run)
    db.flush()  # get run.id without committing yet

    # Determine which test cases to include
    if payload.test_case_ids:
        test_cases = (
            db.query(TestCase)
            .filter(
                TestCase.project_id == project_id,
                TestCase.id.in_(payload.test_case_ids),
                TestCase.status == "active",
            )
            .all()
        )
        # Warn about IDs not found but do not fail
        found_ids = {tc.id for tc in test_cases}
        missing = [tid for tid in payload.test_case_ids if tid not in found_ids]
        if len(test_cases) == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="None of the specified test case IDs were found or are active",
            )
    else:
        test_cases = (
            db.query(TestCase)
            .filter(TestCase.project_id == project_id, TestCase.status == "active")
            .all()
        )

    if not test_cases:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No active test cases available for this run",
        )

    for tc in test_cases:
        result = ExecutionResult(
            id=str(uuid.uuid4()),
            run_id=run_id,
            test_case_id=tc.id,
            status="pending",
        )
        db.add(result)

    db.commit()
    db.refresh(run)
    return _build_run_summary(run)


@router.get("", response_model=List[RunSummary])
def list_runs(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    runs = (
        db.query(ExecutionRun)
        .filter(ExecutionRun.project_id == project_id)
        .order_by(ExecutionRun.created_at.desc())
        .all()
    )
    return [_build_run_summary(r) for r in runs]


@router.get("/{run_id}", response_model=RunSummary)
def get_run(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    run = _get_run_or_404(project_id, run_id, db)
    return _build_run_summary(run)


@router.put("/{run_id}/results/{result_id}", response_model=ExecutionResultResponse)
def update_result(
    project_id: str,
    run_id: str,
    result_id: str,
    payload: ExecutionResultUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    run = _get_run_or_404(project_id, run_id, db)

    if run.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot update results on a completed run",
        )
    if run.status == "abandoned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot update results on an abandoned run",
        )

    if payload.status not in VALID_RESULT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_RESULT_STATUSES)}",
        )

    result = (
        db.query(ExecutionResult)
        .filter(ExecutionResult.id == result_id, ExecutionResult.run_id == run_id)
        .first()
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    result.status = payload.status
    if payload.actual_result is not None:
        result.actual_result = payload.actual_result
    if payload.notes is not None:
        result.notes = payload.notes
    result.updated_at = datetime.utcnow()

    # Update run's updated_at to reflect activity
    run.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(result)
    return result


@router.put("/{run_id}/complete", response_model=RunSummary)
def complete_run(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    run = _get_run_or_404(project_id, run_id, db)

    if run.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run is already completed",
        )
    if run.status == "abandoned":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot complete an abandoned run",
        )

    run.status = "completed"
    run.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(run)
    return _build_run_summary(run)


@router.put("/{run_id}/abandon", response_model=RunSummary)
def abandon_run(
    project_id: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)
    run = _get_run_or_404(project_id, run_id, db)

    if run.status in ("completed", "abandoned"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run is already {run.status}",
        )

    run.status = "abandoned"
    run.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(run)
    return _build_run_summary(run)
