import pytest
from unittest.mock import MagicMock, patch

PROFILE = {
    "preferences": {
        "roles": ["QA Lead", "QA Automation Manager"],
        "locations": ["Remote", "Hybrid"],
        "minimum_salary": "35 LPA",
    },
    "skills": ["Python", "Playwright", "PyTest", "Selenium"],
}


def make_scorer(mock_content):
    with patch("core.job_scorer.ChatGoogleGenerativeAI") as MockLLM:
        mock_response = MagicMock()
        mock_response.content = mock_content
        MockLLM.return_value.invoke.return_value = mock_response
        from core.job_scorer import JobScorer
        scorer = JobScorer()
        scorer.llm = MockLLM.return_value
        return scorer


def test_score_above_threshold_sets_apply_true():
    scorer = make_scorer('{"score": 8, "reason": "Good match", "apply": true}')
    result = scorer.score("QA Lead", "Selenium Playwright automation required", PROFILE)
    assert result["apply"] is True
    assert result["score"] == 8


def test_score_below_threshold_sets_apply_false():
    scorer = make_scorer('{"score": 4, "reason": "Junior role", "apply": false}')
    result = scorer.score("Junior QA", "Manual testing only", PROFILE)
    assert result["apply"] is False


def test_apply_field_overridden_by_threshold():
    scorer = make_scorer('{"score": 7, "reason": "Close match", "apply": false}')
    result = scorer.score("QA Manager", "Automation testing", PROFILE)
    assert result["apply"] is True


def test_malformed_json_retries_and_defaults():
    with patch("core.job_scorer.ChatGoogleGenerativeAI") as MockLLM:
        mock_response = MagicMock()
        mock_response.content = "not json at all"
        MockLLM.return_value.invoke.return_value = mock_response
        from core.job_scorer import JobScorer
        scorer = JobScorer()
        scorer.llm = MockLLM.return_value
        result = scorer.score("QA Lead", "desc", PROFILE)
    assert result["apply"] is True
    assert result["score"] == 5


def test_strips_markdown_code_blocks():
    scorer = make_scorer('```json\n{"score": 9, "reason": "Great", "apply": true}\n```')
    result = scorer.score("QA Lead", "desc", PROFILE)
    assert result["score"] == 9
