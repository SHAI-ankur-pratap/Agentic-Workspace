import os
import asyncio
import pytest
from unittest.mock import MagicMock, patch

SAMPLE_RESUME = """# Ankur Pratap
QA Lead | ankurpratap32@yahoo.in

## SUMMARY
Experienced QA engineer with 8+ years.

## EXPERIENCE
### Shorthills AI — QA Lead (2024–Present)
- Led QA for generative AI products.

## SKILLS
Python, Playwright, PyTest, Selenium
"""


def make_tailor(mock_content, base_resume_path):
    with patch("core.cv_tailor.ChatGoogleGenerativeAI") as MockLLM:
        mock_response = MagicMock()
        mock_response.content = mock_content
        MockLLM.return_value.invoke.return_value = mock_response
        from core.cv_tailor import CVTailor
        tailor = CVTailor(base_cv_path=str(base_resume_path))
        tailor.llm = MockLLM.return_value
        return tailor


def test_rewrite_returns_tailored_content(tmp_path):
    resume_file = tmp_path / "resume.md"
    resume_file.write_text(SAMPLE_RESUME)
    tailored = "# Ankur Pratap\n\n## SUMMARY\nTailored for automation role.\n\n" + "x" * 400
    tailor = make_tailor(tailored, resume_file)
    result = tailor.rewrite_cv("Playwright automation testing role required")
    assert len(result) > 300


def test_rewrite_falls_back_to_base_on_short_response(tmp_path):
    resume_file = tmp_path / "resume.md"
    resume_file.write_text(SAMPLE_RESUME)
    tailor = make_tailor("too short", resume_file)
    result = tailor.rewrite_cv("some JD")
    assert result == SAMPLE_RESUME


def test_generate_pdf_creates_file(tmp_path):
    resume_file = tmp_path / "resume.md"
    resume_file.write_text(SAMPLE_RESUME)
    output_pdf = str(tmp_path / "out.pdf")
    with patch("core.cv_tailor.ChatGoogleGenerativeAI"):
        from core.cv_tailor import CVTailor
        tailor = CVTailor(base_cv_path=str(resume_file))
    asyncio.run(tailor.generate_pdf(SAMPLE_RESUME, output_pdf))
    assert os.path.exists(output_pdf)
    assert os.path.getsize(output_pdf) > 1000
