import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

PROFILE = {
    "personal_info": {"first_name": "Ankur", "last_name": "Pratap", "email": "a@b.com"},
    "preferences": {"minimum_salary": "35 LPA"},
    "qa_bank": [],
}


def make_agent():
    with patch("core.form_filler.ChatGoogleGenerativeAI"):
        from core.form_filler import UniversalFormFiller
        filler = UniversalFormFiller(PROFILE)
        filler.llm = MagicMock()
    from core.external_portal import ExternalPortalAgent
    return ExternalPortalAgent(PROFILE, filler)


def test_detect_workday():
    agent = make_agent()
    assert agent.detect_portal("https://company.myworkdayjobs.com/jobs") == "workday"


def test_detect_greenhouse():
    agent = make_agent()
    assert agent.detect_portal("https://boards.greenhouse.io/company/jobs/123") == "greenhouse"


def test_detect_lever():
    agent = make_agent()
    assert agent.detect_portal("https://jobs.lever.co/company/job-id") == "lever"


def test_detect_generic():
    agent = make_agent()
    assert agent.detect_portal("https://careers.somecompany.com/apply") == "generic"


def test_hard_stop_video_interview(tmp_path):
    agent = make_agent()
    agent.manual_review_file = str(tmp_path / "manual_review.txt")

    page = AsyncMock()
    page.url = "https://company.greenhouse.io/apply"
    page.evaluate = AsyncMock(return_value="please complete a hirevue video interview to apply")

    result = asyncio.run(
        agent.apply(page, "https://example.com/job", "/tmp/cv.pdf")
    )
    assert result == "skipped_hard_stop"
    assert "hirevue" in open(agent.manual_review_file).read().lower()


def test_account_wall_returns_skipped(tmp_path):
    agent = make_agent()
    agent.manual_review_file = str(tmp_path / "manual_review.txt")

    page = AsyncMock()
    page.url = "https://company.greenhouse.io/apply"
    page.evaluate = AsyncMock(return_value="you need to create an account to apply for this job")

    result = asyncio.run(
        agent.apply(page, "https://example.com/job", "/tmp/cv.pdf")
    )
    assert result == "skipped_account_wall"
