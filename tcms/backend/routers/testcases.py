import csv
import io
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import Project, TCIDSequence, Template, TestCase, User
from schemas import (
    CSVImportResponse,
    TemplateImportRequest,
    TestCaseCreate,
    TestCaseResponse,
    TestCaseUpdate,
)

router = APIRouter(prefix="/api/projects/{project_id}/testcases", tags=["testcases"])

VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
VALID_STATUSES = {"draft", "active", "deprecated"}


def _get_project_or_404(project_id: str, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _assign_tc_id(project_id: str, db: Session) -> str:
    """Atomically assign the next TC-ID for the given project using SELECT FOR UPDATE."""
    seq = (
        db.query(TCIDSequence)
        .filter(TCIDSequence.project_id == project_id)
        .with_for_update()
        .first()
    )
    if not seq:
        # Bootstrap sequence for this project
        seq = TCIDSequence(project_id=project_id, next_seq=1)
        db.add(seq)

    tc_id = f"TC-{seq.next_seq:03d}"
    seq.next_seq += 1
    db.flush()  # persist within the current transaction
    return tc_id


@router.get("", response_model=List[TestCaseResponse])
def list_test_cases(
    project_id: str,
    status_filter: str = None,
    priority: str = None,
    component_tag: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    query = db.query(TestCase).filter(TestCase.project_id == project_id)

    if status_filter:
        query = query.filter(TestCase.status == status_filter)
    if priority:
        query = query.filter(TestCase.priority == priority)

    cases = query.order_by(TestCase.tc_id.asc()).all()

    if component_tag:
        cases = [tc for tc in cases if component_tag in (tc.component_tags or [])]

    return cases


@router.post("", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
def create_test_case(
    project_id: str,
    payload: TestCaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    if payload.priority not in VALID_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid priority. Must be one of: {', '.join(VALID_PRIORITIES)}",
        )
    if payload.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
        )

    tc_id = _assign_tc_id(project_id, db)

    test_case = TestCase(
        id=str(uuid.uuid4()),
        project_id=project_id,
        tc_id=tc_id,
        title=payload.title,
        description=payload.description,
        steps=payload.steps,
        expected_result=payload.expected_result,
        priority=payload.priority,
        status=payload.status,
        component_tags=payload.component_tags or [],
        jira_ref=payload.jira_ref,
        is_ai_generated=False,
        created_by=current_user.id,
    )
    db.add(test_case)
    db.commit()
    db.refresh(test_case)
    return test_case


@router.get("/{tc_id}", response_model=TestCaseResponse)
def get_test_case(
    project_id: str,
    tc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    test_case = (
        db.query(TestCase)
        .filter(TestCase.project_id == project_id, TestCase.tc_id == tc_id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    return test_case


@router.put("/{tc_id}", response_model=TestCaseResponse)
def update_test_case(
    project_id: str,
    tc_id: str,
    payload: TestCaseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    test_case = (
        db.query(TestCase)
        .filter(TestCase.project_id == project_id, TestCase.tc_id == tc_id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "priority" in update_data and update_data["priority"] not in VALID_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid priority. Must be one of: {', '.join(VALID_PRIORITIES)}",
        )
    if "status" in update_data and update_data["status"] not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
        )

    for field, value in update_data.items():
        setattr(test_case, field, value)
    test_case.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(test_case)
    return test_case


@router.delete("/{tc_id}", status_code=status.HTTP_200_OK)
def delete_test_case(
    project_id: str,
    tc_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    test_case = (
        db.query(TestCase)
        .filter(TestCase.project_id == project_id, TestCase.tc_id == tc_id)
        .first()
    )
    if not test_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")

    db.delete(test_case)
    db.commit()
    return {"deleted": True}


@router.post("/import-csv", response_model=CSVImportResponse, status_code=status.HTTP_200_OK)
async def import_csv(
    project_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only CSV files are accepted",
        )

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # handle BOM if present
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV file must be UTF-8 encoded",
        )

    reader = csv.DictReader(io.StringIO(text))

    # Validate required column
    if reader.fieldnames is None or "title" not in [f.strip() for f in reader.fieldnames]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV must contain a 'title' column",
        )

    imported = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):  # row 1 is header
        title = row.get("title", "").strip()
        if not title:
            errors.append(f"Row {row_num}: 'title' is empty, skipping")
            continue

        raw_priority = row.get("priority", "P2").strip().upper()
        priority = raw_priority if raw_priority in VALID_PRIORITIES else "P2"

        raw_tags = row.get("component_tags", "").strip()
        component_tags = (
            [t.strip() for t in raw_tags.split(",") if t.strip()] if raw_tags else []
        )

        try:
            tc_id = _assign_tc_id(project_id, db)
            test_case = TestCase(
                id=str(uuid.uuid4()),
                project_id=project_id,
                tc_id=tc_id,
                title=title,
                description=None,
                steps=row.get("steps", "").strip() or "See title",
                expected_result=row.get("expected_result", "").strip() or "See title",
                priority=priority,
                status="active",
                component_tags=component_tags,
                jira_ref=None,
                is_ai_generated=False,
                created_by=current_user.id,
            )
            db.add(test_case)
            imported += 1
        except Exception as exc:
            errors.append(f"Row {row_num}: {str(exc)}")

    db.commit()
    return CSVImportResponse(imported=imported, errors=errors)


@router.post("/import-template", response_model=CSVImportResponse, status_code=status.HTTP_200_OK)
def import_template(
    project_id: str,
    payload: TemplateImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_project_or_404(project_id, db)

    template = db.query(Template).filter(Template.type == payload.template_type).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{payload.template_type}' not found",
        )

    cases: list[dict] = template.cases or []
    imported = 0
    errors: list[str] = []

    for idx, case_data in enumerate(cases):
        title = (case_data.get("title") or "").strip()
        if not title:
            errors.append(f"Template case {idx + 1}: missing title, skipping")
            continue

        raw_priority = (case_data.get("priority") or "P2").strip().upper()
        priority = raw_priority if raw_priority in VALID_PRIORITIES else "P2"

        component_tags = case_data.get("component_tags") or []
        if isinstance(component_tags, str):
            component_tags = [t.strip() for t in component_tags.split(",") if t.strip()]

        try:
            tc_id = _assign_tc_id(project_id, db)
            test_case = TestCase(
                id=str(uuid.uuid4()),
                project_id=project_id,
                tc_id=tc_id,
                title=title,
                description=case_data.get("description"),
                steps=case_data.get("steps") or "See title",
                expected_result=case_data.get("expected_result") or "See title",
                priority=priority,
                status="active",
                component_tags=component_tags,
                jira_ref=case_data.get("jira_ref"),
                is_ai_generated=False,
                created_by=current_user.id,
            )
            db.add(test_case)
            imported += 1
        except Exception as exc:
            errors.append(f"Template case {idx + 1}: {str(exc)}")

    db.commit()
    return CSVImportResponse(imported=imported, errors=errors)
