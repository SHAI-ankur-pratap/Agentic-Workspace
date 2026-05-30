from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator


# --- Auth ---
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class APIKeyCreate(BaseModel):
    name: str


class APIKeyResponse(BaseModel):
    id: str
    name: str
    raw_key: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Users ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "qa_lead"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    digest_opt_out: bool
    created_at: datetime

    class Config:
        from_attributes = True


# --- Projects ---
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    client_name: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    github_repo: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    client_name: Optional[str] = None
    status: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    github_repo: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    client_name: Optional[str]
    status: str
    created_by: str
    slack_webhook_url: Optional[str]
    github_repo: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectStats(BaseModel):
    project: ProjectResponse
    total_cases: int
    coverage_pct: float
    last_run_at: Optional[datetime]
    days_since_last_run: Optional[int]
    needs_attention: bool


# --- Component Tag Rules ---
class ComponentTagRuleCreate(BaseModel):
    file_pattern: str
    component_tag: str


class ComponentTagRuleResponse(BaseModel):
    id: str
    project_id: str
    file_pattern: str
    component_tag: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- Test Cases ---
class TestCaseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    steps: str
    expected_result: str
    priority: str = "P2"
    status: str = "active"
    component_tags: Optional[List[str]] = []
    jira_ref: Optional[str] = None


class TestCaseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    steps: Optional[str] = None
    expected_result: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    component_tags: Optional[List[str]] = None
    jira_ref: Optional[str] = None


class TestCaseResponse(BaseModel):
    id: str
    project_id: str
    tc_id: str
    title: str
    description: Optional[str]
    steps: str
    expected_result: str
    priority: str
    status: str
    component_tags: List[str]
    jira_ref: Optional[str]
    is_ai_generated: bool
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CSVImportResponse(BaseModel):
    imported: int
    errors: List[str]


class TemplateImportRequest(BaseModel):
    template_type: str


# --- Execution Runs ---
class ExecutionRunCreate(BaseModel):
    name: str
    test_case_ids: Optional[List[str]] = None


class ExecutionRunResponse(BaseModel):
    id: str
    project_id: str
    name: str
    status: str
    is_live: bool
    executive_summary: Optional[str]
    github_pr_number: Optional[int]
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExecutionResultUpdate(BaseModel):
    status: str
    actual_result: Optional[str] = None
    notes: Optional[str] = None


class ExecutionResultResponse(BaseModel):
    id: str
    run_id: str
    test_case_id: str
    status: str
    actual_result: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RunSummary(BaseModel):
    run: ExecutionRunResponse
    total: int
    passed: int
    failed: int
    skipped: int
    blocked: int
    pending: int
    coverage_pct: float
    results: List["ExecutionResultResponse"] = []


# --- Reports / Share ---
class ShareLinkResponse(BaseModel):
    token: str
    url: str
    expires_at: datetime


# --- AI ---
class GenerateRequest(BaseModel):
    project_id: Optional[str] = None
    user_story: str
    count: int = 10


class GeneratedTestCase(BaseModel):
    title: str
    steps: str
    expected_result: str
    priority: str


class GenerateResponse(BaseModel):
    test_cases: List[GeneratedTestCase]


class CriticizeRequest(BaseModel):
    test_case_id: str


class Suggestion(BaseModel):
    type: str
    description: str
    rewrite: Optional[str] = None


class CriticizeResponse(BaseModel):
    suggestions: List[Suggestion]


# --- Webhooks ---
class GitHubWebhookPayload(BaseModel):
    action: Optional[str] = None
    number: Optional[int] = None
    pull_request: Optional[dict] = None
    repository: Optional[dict] = None
