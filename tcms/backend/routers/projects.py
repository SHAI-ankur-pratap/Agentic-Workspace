import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import ComponentTagRule, ExecutionRun, Project, TestCase, User
from schemas import (
    ComponentTagRuleCreate,
    ComponentTagRuleResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectStats,
    ProjectUpdate,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _compute_project_stats(project: Project, db: Session) -> ProjectStats:
    total_cases = (
        db.query(TestCase)
        .filter(TestCase.project_id == project.id, TestCase.status == "active")
        .count()
    )

    # Find the last completed run for coverage
    last_completed_run = (
        db.query(ExecutionRun)
        .filter(
            ExecutionRun.project_id == project.id,
            ExecutionRun.status == "completed",
        )
        .order_by(ExecutionRun.updated_at.desc())
        .first()
    )

    coverage_pct = 0.0
    last_run_at: Optional[datetime] = None
    days_since_last_run: Optional[int] = None

    if last_completed_run:
        last_run_at = last_completed_run.updated_at
        now = datetime.utcnow()
        delta = now - last_run_at
        days_since_last_run = delta.days

        # Calculate coverage from last completed run results
        results = last_completed_run.results
        if results:
            total = len(results)
            passed = sum(1 for r in results if r.status == "pass")
            coverage_pct = (passed / total * 100) if total > 0 else 0.0

    needs_attention = coverage_pct < 70 or (
        days_since_last_run is not None and days_since_last_run > 14
    )
    # Also flag if there's never been a run
    if last_run_at is None and total_cases > 0:
        needs_attention = True

    return ProjectStats(
        project=ProjectResponse.model_validate(project),
        total_cases=total_cases,
        coverage_pct=round(coverage_pct, 2),
        last_run_at=last_run_at,
        days_since_last_run=days_since_last_run,
        needs_attention=needs_attention,
    )


@router.get("", response_model=List[ProjectStats])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    projects = (
        db.query(Project)
        .filter(Project.status == "active")
        .order_by(Project.updated_at.desc())
        .all()
    )

    stats_list = [_compute_project_stats(p, db) for p in projects]

    # Sort: needs_attention first, then by project.updated_at desc
    stats_list.sort(
        key=lambda s: (0 if s.needs_attention else 1, -s.project.updated_at.timestamp())
    )
    return stats_list


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(
        id=str(uuid.uuid4()),
        name=payload.name,
        description=payload.description,
        client_name=payload.client_name,
        slack_webhook_url=payload.slack_webhook_url,
        github_repo=payload.github_repo,
        created_by=current_user.id,
        status="active",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)
    project.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"deleted": True}


# --- Component Tag Rules ---


@router.post(
    "/{project_id}/component-tag-rules",
    response_model=ComponentTagRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_component_tag_rule(
    project_id: str,
    payload: ComponentTagRuleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    rule = ComponentTagRule(
        id=str(uuid.uuid4()),
        project_id=project_id,
        file_pattern=payload.file_pattern,
        component_tag=payload.component_tag,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get(
    "/{project_id}/component-tag-rules",
    response_model=List[ComponentTagRuleResponse],
)
def list_component_tag_rules(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    rules = (
        db.query(ComponentTagRule)
        .filter(ComponentTagRule.project_id == project_id)
        .order_by(ComponentTagRule.created_at.asc())
        .all()
    )
    return rules


@router.delete(
    "/{project_id}/component-tag-rules/{rule_id}",
    status_code=status.HTTP_200_OK,
)
def delete_component_tag_rule(
    project_id: str,
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = (
        db.query(ComponentTagRule)
        .filter(
            ComponentTagRule.id == rule_id,
            ComponentTagRule.project_id == project_id,
        )
        .first()
    )
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )
    db.delete(rule)
    db.commit()
    return {"deleted": True}
