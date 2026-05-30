import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime, ForeignKey,
    JSON, Enum as SAEnum, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from database import Base


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=_uuid)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(SAEnum("admin", "qa_lead", "delivery_head", name="user_role"), default="qa_lead")
    is_active = Column(Boolean, default=True)
    digest_opt_out = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="created_by_user")


class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="api_keys")


class Project(Base):
    __tablename__ = "projects"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    client_name = Column(String(255), nullable=True)
    status = Column(SAEnum("active", "archived", name="project_status"), default="active")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    slack_webhook_url = Column(String(500), nullable=True)
    github_repo = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by_user = relationship("User", back_populates="projects")
    test_cases = relationship("TestCase", back_populates="project", cascade="all, delete-orphan")
    execution_runs = relationship("ExecutionRun", back_populates="project", cascade="all, delete-orphan")
    component_tag_rules = relationship("ComponentTagRule", back_populates="project", cascade="all, delete-orphan")
    tc_sequence = relationship("TCIDSequence", back_populates="project", uselist=False, cascade="all, delete-orphan")


class TCIDSequence(Base):
    """Per-project TC-ID sequence counter (Decision 6: scoped TC-IDs)."""
    __tablename__ = "tcid_sequences"
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    next_seq = Column(Integer, default=1, nullable=False)

    project = relationship("Project", back_populates="tc_sequence")


class ComponentTagRule(Base):
    """Maps file glob patterns to component tags for GitHub PR integration (Decision 18)."""
    __tablename__ = "component_tag_rules"
    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_pattern = Column(String(255), nullable=False)
    component_tag = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="component_tag_rules")


class TestCase(Base):
    __tablename__ = "test_cases"
    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    tc_id = Column(String(20), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    steps = Column(Text, nullable=False)
    expected_result = Column(Text, nullable=False)
    priority = Column(SAEnum("P1", "P2", "P3", "P4", name="priority_level"), default="P2")
    status = Column(SAEnum("draft", "active", "deprecated", name="tc_status"), default="active")
    component_tags = Column(JSON, default=list)
    jira_ref = Column(String(100), nullable=True)
    is_ai_generated = Column(Boolean, default=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("project_id", "tc_id", name="uq_project_tcid"),)

    project = relationship("Project", back_populates="test_cases")
    execution_results = relationship("ExecutionResult", back_populates="test_case")


class ExecutionRun(Base):
    __tablename__ = "execution_runs"
    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(SAEnum("in_progress", "completed", "abandoned", name="run_status"), default="in_progress")
    is_live = Column(Boolean, default=False)
    executive_summary = Column(Text, nullable=True)
    executive_summary_cached_at = Column(DateTime, nullable=True)
    github_pr_number = Column(Integer, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="execution_runs")
    results = relationship("ExecutionResult", back_populates="run", cascade="all, delete-orphan")
    share_tokens = relationship("ShareToken", back_populates="run", cascade="all, delete-orphan")


class ExecutionResult(Base):
    __tablename__ = "execution_results"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False)
    test_case_id = Column(String(36), ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False)
    status = Column(SAEnum("pass", "fail", "skip", "blocked", "pending", name="result_status"), default="pending")
    actual_result = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    run = relationship("ExecutionRun", back_populates="results")
    test_case = relationship("TestCase", back_populates="execution_results")


class ShareToken(Base):
    __tablename__ = "share_tokens"
    id = Column(String(36), primary_key=True, default=_uuid)
    run_id = Column(String(36), ForeignKey("execution_runs.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("ExecutionRun", back_populates="share_tokens")


class Template(Base):
    __tablename__ = "templates"
    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    type = Column(SAEnum("react-crud", "rest-api", "mobile", name="template_type"), unique=True, nullable=False)
    cases = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
