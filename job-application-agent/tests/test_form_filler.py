import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

PROFILE = {
    "personal_info": {
        "first_name": "Ankur", "last_name": "Pratap",
        "email": "ankurpratap32@yahoo.in", "phone": "+91-9113572745",
        "location": "Delhi, 110075",
    },
    "preferences": {"minimum_salary": "35 LPA", "current_salary": "25 LPA"},
    "qa_bank": [
        {"question": "Notice Period", "answer": "1 month"},
        {"question": "Will you require visa sponsorship?", "answer": "No"},
    ],
}

SAMPLE_INPUTS = [
    {"id": "email", "name": "email", "type": "email", "label": "Email", "options": []},
    {"id": "phone", "name": "phone", "type": "tel", "label": "Phone Number", "options": []},
    {"id": "salary", "name": "salary", "type": "text", "label": "Expected Salary", "options": []},
]


def make_filler(mock_content):
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = mock_content
    mock_llm.invoke.return_value = mock_response
    with patch("core.llm_client.build_llm", return_value=mock_llm):
        from core.form_filler import UniversalFormFiller
        filler = UniversalFormFiller(PROFILE)
    filler.llm = mock_llm
    return filler


def test_skips_account_wall_on_workday():
    filler = make_filler("{}")
    page = AsyncMock()
    page.url = "https://company.myworkdayjobs.com/apply"
    page.evaluate = AsyncMock(return_value="create account to apply workday login")
    result = asyncio.run(
        filler.parse_and_fill(page, page.url)
    )
    assert result is False


def test_returns_true_when_no_fields():
    filler = make_filler("{}")
    page = AsyncMock()
    page.url = "https://example.com"
    page.evaluate = AsyncMock(side_effect=["no account wall", []])
    result = asyncio.run(
        filler.parse_and_fill(page, page.url)
    )
    assert result is True


def test_skip_field_logs_to_manual_review(tmp_path):
    manual_file = tmp_path / "manual_review.txt"
    filler = make_filler('{"salary": "__SKIP__"}')
    filler.manual_review_file = str(manual_file)

    page = AsyncMock()
    page.url = "https://example.com/apply"
    page.evaluate = AsyncMock(side_effect=["no wall text", SAMPLE_INPUTS])
    page.fill = AsyncMock()
    asyncio.run(
        filler.parse_and_fill(page, page.url)
    )
    assert manual_file.exists()
    assert "salary" in manual_file.read_text()
