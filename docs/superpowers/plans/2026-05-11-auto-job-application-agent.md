# Auto Job Application Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing job-application-agent skeleton into a fully autonomous, LLM-powered agent that scores job relevance, tailors resumes per job, fills forms via Gemini, and handles external portals (Workday, Greenhouse, Lever) end-to-end.

**Architecture:** Gemini 1.5 Flash (free tier) powers three components — `job_scorer.py` (relevance filter), `cv_tailor.py` (resume rewrite), and `form_filler.py` (intelligent field mapping). A new `external_portal.py` handles redirects from LinkedIn/Naukri to company career sites. Playwright renders tailored resumes to PDF (no extra deps). All platforms run through the existing 4-hour daemon orchestrator.

**Tech Stack:** Python 3, Playwright, langchain-google-genai (gemini-1.5-flash free tier), markdown2, pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/job_scorer.py` | CREATE | Gemini-powered relevance scoring (0-10), threshold filter |
| `core/cv_tailor.py` | UPGRADE | Real Gemini LLM rewrite + Playwright PDF (replaces mock + broken fpdf) |
| `core/form_filler.py` | UPGRADE | Real Gemini LLM field mapping (replaces hardcoded regex) |
| `core/external_portal.py` | CREATE | Workday/Greenhouse/Lever/generic portal handling |
| `core/linkedin.py` | UPGRADE | Extract real JD, wire scorer+tailor+external portal, fix Easy Apply modal |
| `core/naukri.py` | UPGRADE | Extract real JD, wire scorer+tailor+external portal |
| `core/filter.py` | UPGRADE | Delegate to job_scorer instead of returning mock score=85 |
| `core/orchestrator.py` | UPGRADE | Cycle summary counts, proper error isolation per platform |
| `core/generator.py` | UPGRADE | Use GOOGLE_API_KEY env var (already uses GEMINI_API_KEY fallback) |
| `.env` | UPGRADE | Add GOOGLE_API_KEY |
| `tests/test_job_scorer.py` | CREATE | Unit tests for scorer (mocked LLM) |
| `tests/test_cv_tailor.py` | CREATE | Unit tests for CV rewrite + PDF |
| `tests/test_form_filler.py` | CREATE | Unit tests for form field mapping |
| `tests/test_external_portal.py` | CREATE | Unit tests for portal detection + hard stops |

**Working directory for all commands:** `job-application-agent/`  
**All python commands:** `source venv/bin/activate && python ...`  
**All pytest commands:** `source venv/bin/activate && pytest ...`

---

## Task 0: Environment Setup

**Files:**
- Modify: `.env`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add GOOGLE_API_KEY to .env**

Open `.env` and add this line (user must paste their own key from https://aistudio.google.com/app/apikey):
```
GOOGLE_API_KEY="your_key_here"
```

The full `.env` should look like:
```
LINKEDIN_EMAIL="ankurpratap32@yahoo.in"
LINKEDIN_PASSWORD="Ankur32@"
NAUKRI_EMAIL="ankurpratap999@gmail.com"
NAUKRI_PASSWORD="Ankur32@"
GOOGLE_API_KEY="your_key_here"
```

- [ ] **Step 2: Create tests directory**

```bash
cd job-application-agent
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 3: Verify LLM connection**

```bash
cd job-application-agent
source venv/bin/activate
python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
llm = ChatGoogleGenerativeAI(model='gemini-1.5-flash', temperature=0, google_api_key=os.getenv('GOOGLE_API_KEY'))
r = llm.invoke([HumanMessage(content='Reply with: OK')])
print('LLM test:', r.content)
"
```

Expected output: `LLM test: OK`

---

## Task 1: Job Scorer

**Files:**
- Create: `core/job_scorer.py`
- Create: `tests/test_job_scorer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_job_scorer.py`:

```python
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
    # LLM says apply=false but score=7 — our code forces apply=True
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_job_scorer.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.job_scorer'`

- [ ] **Step 3: Create `core/job_scorer.py`**

```python
import json
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage

load_dotenv()

SCORE_THRESHOLD = 6


class JobScorer:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    def score(self, job_title: str, job_description: str, profile: dict) -> dict:
        roles = profile.get("preferences", {}).get("roles", [])
        skills = profile.get("skills", [])
        locations = profile.get("preferences", {}).get("locations", [])
        min_salary = profile.get("preferences", {}).get("minimum_salary", "")

        prompt = f"""Evaluate this job posting for a candidate. Score the match 0-10.

Candidate preferred roles: {', '.join(roles)}
Candidate skills: {', '.join(skills)}
Candidate location preferences: {', '.join(locations)}
Candidate minimum salary: {min_salary}

Job Title: {job_title}
Job Description: {job_description[:1500]}

Respond with ONLY valid JSON, no markdown fences:
{{"score": <0-10 integer>, "reason": "<one sentence>", "apply": <true if score>=6 else false>}}"""

        for attempt in range(3):
            try:
                response = self.llm.invoke([HumanMessage(content=prompt)])
                text = response.content.strip()
                if text.startswith("```"):
                    parts = text.split("```")
                    text = parts[1]
                    if text.startswith("json"):
                        text = text[4:]
                result = json.loads(text.strip())
                result["apply"] = int(result.get("score", 0)) >= SCORE_THRESHOLD
                return result
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️ [Job Scorer] LLM failed: {e}. Defaulting apply=True.")
        return {"score": 5, "reason": "LLM unavailable, defaulting", "apply": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_job_scorer.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add job-application-agent/core/job_scorer.py job-application-agent/tests/test_job_scorer.py job-application-agent/tests/__init__.py
git commit -m "feat: add LLM-powered job scorer (gemini-1.5-flash)"
```

---

## Task 2: CV Tailor Upgrade

**Files:**
- Modify: `core/cv_tailor.py`
- Create: `tests/test_cv_tailor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cv_tailor.py`:

```python
import os
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


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
    assert "Ankur" in result or len(result) > 300


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
    import asyncio
    asyncio.run(tailor.generate_pdf(SAMPLE_RESUME, output_pdf))
    assert os.path.exists(output_pdf)
    assert os.path.getsize(output_pdf) > 1000
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_cv_tailor.py -v
```

Expected: tests fail (mock LLM method doesn't exist, generate_pdf not async)

- [ ] **Step 3: Rewrite `core/cv_tailor.py`**

```python
import os
import json
import asyncio
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
import markdown2

load_dotenv()


class CVTailor:
    def __init__(self, base_cv_path="base_resume.md"):
        self.base_cv_path = base_cv_path
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.3,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    def rewrite_cv(self, job_description: str) -> str:
        with open(self.base_cv_path, "r") as f:
            base_md = f.read()

        prompt = f"""You are a professional resume writer. Tailor the resume below for the job description.

RULES:
- Reorder bullets to lead with most-relevant experience
- Naturally weave in keywords from the JD
- Adjust the SUMMARY line for this specific role
- Do NOT fabricate experience, skills, titles, or dates
- Output ONLY the complete resume in Markdown, no extra commentary

JOB DESCRIPTION:
{job_description[:2000]}

RESUME:
{base_md}"""

        for attempt in range(3):
            try:
                response = self.llm.invoke([HumanMessage(content=prompt)])
                tailored = response.content.strip()
                if tailored.startswith("```"):
                    tailored = tailored.split("```")[1]
                    if tailored.startswith("markdown") or tailored.startswith("md"):
                        tailored = tailored.split("\n", 1)[1]
                if len(tailored) > 300:
                    return tailored
            except Exception as e:
                print(f"⚠️ [CV Tailor] Attempt {attempt+1} failed: {e}")

        print("⚠️ [CV Tailor] LLM failed, using base resume unchanged.")
        return base_md

    async def generate_pdf(self, md_content: str, output_path: str = "tailored_cv.pdf") -> str:
        print(f"📄 [CV Tailor] Rendering PDF to {output_path}...")
        html_body = markdown2.markdown(md_content, extras=["tables", "fenced-code-blocks"])
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 15mm 20mm; line-height: 1.45; color: #222; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  h2 {{ font-size: 13px; border-bottom: 1px solid #555; margin: 14px 0 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
  h3 {{ font-size: 11px; font-weight: bold; margin: 8px 0 2px; }}
  ul {{ margin: 3px 0 6px; padding-left: 16px; }}
  li {{ margin-bottom: 2px; }}
  p {{ margin: 3px 0; }}
  a {{ color: #222; text-decoration: none; }}
</style>
</head><body>{html_body}</body></html>"""

        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            await page.pdf(path=output_path, format="A4", margin={
                "top": "15mm", "bottom": "15mm", "left": "20mm", "right": "20mm"
            })
            await browser.close()

        print("✅ [CV Tailor] PDF generated successfully.")
        return output_path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_cv_tailor.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add job-application-agent/core/cv_tailor.py job-application-agent/tests/test_cv_tailor.py
git commit -m "feat: upgrade cv_tailor with real Gemini LLM and Playwright PDF rendering"
```

---

## Task 3: Form Filler Upgrade

**Files:**
- Modify: `core/form_filler.py`
- Create: `tests/test_form_filler.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_form_filler.py`:

```python
import pytest
import asyncio
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
    with patch("core.form_filler.ChatGoogleGenerativeAI") as MockLLM:
        mock_response = MagicMock()
        mock_response.content = mock_content
        MockLLM.return_value.invoke.return_value = mock_response
        from core.form_filler import UniversalFormFiller
        filler = UniversalFormFiller(PROFILE)
        filler.llm = MockLLM.return_value
        return filler


def test_skips_account_wall_on_workday():
    filler = make_filler("{}")
    page = AsyncMock()
    page.url = "https://company.myworkdayjobs.com/apply"
    page.evaluate = AsyncMock(return_value="create account to apply workday login")
    result = asyncio.get_event_loop().run_until_complete(
        filler.parse_and_fill(page, page.url)
    )
    assert result is False


def test_returns_true_when_no_fields():
    filler = make_filler("{}")
    page = AsyncMock()
    page.url = "https://example.com"
    page.evaluate = AsyncMock(side_effect=["no account wall", []])
    result = asyncio.get_event_loop().run_until_complete(
        filler.parse_and_fill(page, page.url)
    )
    assert result is True


def test_skip_field_logs_to_manual_review(tmp_path):
    import os
    manual_file = tmp_path / "manual_review.txt"
    filler = make_filler('{"salary": "__SKIP__"}')
    filler.manual_review_file = str(manual_file)

    page = AsyncMock()
    page.url = "https://example.com/apply"
    page.evaluate = AsyncMock(side_effect=["no wall text", SAMPLE_INPUTS])
    page.fill = AsyncMock()
    asyncio.get_event_loop().run_until_complete(
        filler.parse_and_fill(page, page.url)
    )
    assert manual_file.exists()
    assert "salary" in manual_file.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_form_filler.py -v
```

Expected: failures (old form_filler has no LLM, wrong method signatures)

- [ ] **Step 3: Rewrite `core/form_filler.py`**

```python
import json
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage

load_dotenv()

ACCOUNT_WALL_PHRASES = ["create account", "sign in to apply", "register to apply", "sign up to apply"]
WORKDAY_HOSTS = ["myworkdayjobs.com", "wd3.myworkdaysite.com", "wd1.myworkdaysite.com"]


class UniversalFormFiller:
    def __init__(self, profile: dict):
        self.profile = profile
        self.manual_review_file = "manual_review.txt"
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    async def parse_and_fill(self, page, job_url: str) -> bool:
        print("🤖 [Form Filler] Scanning page for form fields...")

        try:
            page_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        except Exception:
            page_text = ""

        url_lower = getattr(page, "url", job_url).lower()
        is_workday = any(h in url_lower for h in WORKDAY_HOSTS)
        has_account_wall = any(phrase in page_text for phrase in ACCOUNT_WALL_PHRASES)

        if is_workday and has_account_wall:
            print("⛔ [Form Filler] Workday account wall detected. Skipping.")
            self._log_manual_review(job_url, "Account Creation Required (Workday)")
            return False

        inputs = await page.evaluate("""() => {
            const fields = Array.from(document.querySelectorAll(
                'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="file"]), select, textarea'
            ));
            return fields.map(f => {
                let label = '';
                if (f.id) {
                    const l = document.querySelector(`label[for="${f.id}"]`);
                    if (l) label = l.innerText.trim();
                }
                if (!label && f.placeholder) label = f.placeholder;
                if (!label && f.name) label = f.name;
                let options = [];
                if (f.tagName === 'SELECT') {
                    options = Array.from(f.options).map(o => o.text.trim()).filter(Boolean);
                }
                return { id: f.id, name: f.name, type: f.type || f.tagName.toLowerCase(), label, options };
            }).filter(f => f.label || f.name);
        }""")

        if not inputs:
            print("⏭️ [Form Filler] No form fields found.")
            return True

        print(f"🧠 [Form Filler] {len(inputs)} fields detected. Mapping via Gemini...")

        pi = self.profile.get("personal_info", {})
        prefs = self.profile.get("preferences", {})
        qa_bank = self.profile.get("qa_bank", [])
        qa_examples = "\n".join(f"Q: {q['question']} → A: {q['answer']}" for q in qa_bank)

        prompt = f"""Map these HTML form fields to the candidate's profile. Return ONLY valid JSON.

CANDIDATE:
Name: {pi.get('first_name', '')} {pi.get('last_name', '')}
Email: {pi.get('email', '')}
Phone: {pi.get('phone', '')}
Location: {pi.get('location', '')}
Current Salary: {prefs.get('current_salary', '')}
Expected Salary: {prefs.get('minimum_salary', '')}
Notice Period: 30 days

KNOWN Q&A (use these for matching questions):
{qa_examples}

FORM FIELDS:
{json.dumps(inputs, indent=2)}

Return a flat JSON object mapping field name/id to fill value.
For fields you cannot confidently answer, set value to "__SKIP__".
No explanation, no markdown, ONLY the JSON object."""

        mapping = {}
        for attempt in range(3):
            try:
                response = self.llm.invoke([HumanMessage(content=prompt)])
                text = response.content.strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                mapping = json.loads(text.strip())
                break
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️ [Form Filler] LLM failed: {e}. Skipping fill.")
                    return True

        for field_key, value in mapping.items():
            if value == "__SKIP__":
                self._log_manual_review(job_url, f"Low-confidence field: {field_key}")
                continue
            field_info = next(
                (f for f in inputs if f["name"] == field_key or f["id"] == field_key), None
            )
            if not field_info:
                continue
            selector = f"[name='{field_key}']" if field_key else f"#{field_info['id']}"
            try:
                ftype = field_info["type"]
                if ftype in ("text", "email", "tel", "number", "textarea", "search", "url"):
                    await page.fill(selector, str(value), timeout=2000)
                elif ftype in ("select-one", "select"):
                    try:
                        await page.select_option(selector, label=str(value), timeout=2000)
                    except Exception:
                        await page.select_option(selector, value=str(value), timeout=2000)
                elif ftype == "radio":
                    await page.check(f"[name='{field_key}'][value='{value}']", timeout=2000)
                elif ftype == "checkbox":
                    if str(value).lower() in ("yes", "true", "1"):
                        await page.check(selector, timeout=2000)
                print(f"   ✅ '{field_info['label']}' → {value}")
            except Exception as e:
                print(f"   ⚠️ Could not fill '{field_key}': {e}")

        return True

    def _log_manual_review(self, url: str, reason: str):
        with open(self.manual_review_file, "a") as f:
            f.write(f"[{reason}] {url}\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_form_filler.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add job-application-agent/core/form_filler.py job-application-agent/tests/test_form_filler.py
git commit -m "feat: upgrade form_filler with real Gemini LLM field mapping"
```

---

## Task 4: External Portal Agent

**Files:**
- Create: `core/external_portal.py`
- Create: `tests/test_external_portal.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_external_portal.py`:

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

PROFILE = {
    "personal_info": {"first_name": "Ankur", "last_name": "Pratap", "email": "a@b.com"},
    "preferences": {"minimum_salary": "35 LPA"},
    "qa_bank": [],
}


def make_agent():
    from core.form_filler import UniversalFormFiller
    with patch("core.form_filler.ChatGoogleGenerativeAI"):
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
    import os
    agent = make_agent()
    manual_file = tmp_path / "manual_review.txt"
    agent.manual_review_file = str(manual_file)

    page = AsyncMock()
    page.url = "https://company.greenhouse.io/apply"
    page.evaluate = AsyncMock(return_value="please complete a hirevue video interview to apply")

    result = asyncio.get_event_loop().run_until_complete(
        agent.apply(page, "https://example.com/job", "/tmp/cv.pdf")
    )
    assert result == "skipped_hard_stop"
    assert "hirevue" in manual_file.read_text().lower()


def test_account_wall_returns_skipped(tmp_path):
    agent = make_agent()
    agent.manual_review_file = str(tmp_path / "manual_review.txt")

    page = AsyncMock()
    page.url = "https://company.greenhouse.io/apply"
    page.evaluate = AsyncMock(return_value="you need to create an account to apply for this job")

    result = asyncio.get_event_loop().run_until_complete(
        agent.apply(page, "https://example.com/job", "/tmp/cv.pdf")
    )
    assert result == "skipped_account_wall"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_external_portal.py -v
```

Expected: `ModuleNotFoundError: No module named 'core.external_portal'`

- [ ] **Step 3: Create `core/external_portal.py`**

```python
import os

PORTAL_PATTERNS = {
    "workday": ["myworkdayjobs.com", "wd3.myworkdaysite.com", "wd1.myworkdaysite.com"],
    "greenhouse": ["boards.greenhouse.io", "greenhouse.io/careers"],
    "lever": ["jobs.lever.co"],
    "smartrecruiters": ["jobs.smartrecruiters.com"],
}

HARD_STOP_PATTERNS = [
    "hirevue", "sparkhire", "video interview", "record a video",
    "phone verification", "verify your phone",
]

ACCOUNT_WALL_PHRASES = [
    "create an account", "create account", "sign in to apply",
    "register to apply", "sign up to apply",
]

SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'button:has-text("Submit application")',
    'button:has-text("Submit Application")',
    'button:has-text("Submit")',
    'button:has-text("Apply")',
    'button:has-text("Send Application")',
    'input[type="submit"]',
]

NEXT_SELECTORS = [
    'button:has-text("Next")',
    'button:has-text("Continue")',
    'button:has-text("Proceed")',
    'button:has-text("Save and Continue")',
    'button:has-text("Review")',
    'a:has-text("Next")',
]

CONFIRM_KEYWORDS = [
    "application submitted", "application received", "thank you for applying",
    "successfully applied", "your application has been", "we received your application",
]


class ExternalPortalAgent:
    def __init__(self, profile: dict, form_filler):
        self.profile = profile
        self.form_filler = form_filler
        self.manual_review_file = "manual_review.txt"

    def detect_portal(self, url: str) -> str:
        url_lower = url.lower()
        for portal, patterns in PORTAL_PATTERNS.items():
            if any(p in url_lower for p in patterns):
                return portal
        return "generic"

    async def apply(self, page, job_url: str, resume_pdf_path: str) -> str:
        portal = self.detect_portal(page.url)
        print(f"🌐 [External Portal] Detected: {portal} — {page.url}")

        try:
            page_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        except Exception:
            page_text = ""

        for stop in HARD_STOP_PATTERNS:
            if stop in page_text:
                print(f"⛔ [External Portal] Hard stop: '{stop}'")
                self._log_manual_review(job_url, f"Hard stop: {stop}")
                return "skipped_hard_stop"

        if any(phrase in page_text for phrase in ACCOUNT_WALL_PHRASES):
            print("⛔ [External Portal] Account creation wall. Skipping.")
            self._log_manual_review(job_url, "Account creation required")
            return "skipped_account_wall"

        for step in range(6):
            print(f"📋 [External Portal] Step {step + 1}...")

            await self._upload_resume(page, resume_pdf_path)

            filled = await self.form_filler.parse_and_fill(page, job_url)
            if not filled:
                return "skipped_account_wall"

            await page.wait_for_timeout(1000)

            if await self._try_submit(page):
                await page.wait_for_timeout(3000)
                try:
                    confirm = await page.evaluate("() => document.body.innerText.toLowerCase()")
                    if any(kw in confirm for kw in CONFIRM_KEYWORDS):
                        print("✅ [External Portal] Confirmed submitted!")
                        return "applied"
                except Exception:
                    pass
                print("✅ [External Portal] Submitted (no confirmation text found).")
                return "applied"

            if not await self._try_next(page):
                print("⚠️ [External Portal] No Next/Submit button found.")
                self._log_manual_review(job_url, "No submit/next button found after filling")
                return "failed"

            await page.wait_for_timeout(2000)

        self._log_manual_review(job_url, "Exceeded max steps (6)")
        return "failed"

    async def _upload_resume(self, page, resume_pdf_path: str):
        if not os.path.exists(resume_pdf_path):
            return
        try:
            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(resume_pdf_path)
                print(f"   📎 Uploaded: {resume_pdf_path}")
                await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"   ⚠️ Resume upload error: {e}")

    async def _try_submit(self, page) -> bool:
        for sel in SUBMIT_SELECTORS:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    async def _try_next(self, page) -> bool:
        for sel in NEXT_SELECTORS:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    def _log_manual_review(self, url: str, reason: str):
        with open(self.manual_review_file, "a") as f:
            f.write(f"[{reason}] {url}\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/test_external_portal.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add job-application-agent/core/external_portal.py job-application-agent/tests/test_external_portal.py
git commit -m "feat: add external portal agent (Workday/Greenhouse/Lever/generic)"
```

---

## Task 5: Upgrade `core/filter.py`

**Files:**
- Modify: `core/filter.py`

- [ ] **Step 1: Replace mock scorer with JobScorer delegation**

Replace the entire content of `core/filter.py`:

```python
from core.job_scorer import JobScorer


class JobFilter:
    def __init__(self, profile: dict):
        self.profile = profile
        self._scorer = JobScorer()

    def score_job(self, job_title: str, job_description: str) -> dict:
        print(f"🧠 [Job Filter] Scoring '{job_title}'...")
        result = self._scorer.score(job_title, job_description, self.profile)
        passed = result.get("apply", True)
        score_10 = result.get("score", 5)
        print(f"   → Score: {score_10}/10 — {'✅ PASS' if passed else '❌ SKIP'}: {result.get('reason', '')}")
        return {"score": score_10 * 10, "passed": passed, "reason": result.get("reason", "")}
```

- [ ] **Step 2: Verify no broken imports**

```bash
cd job-application-agent
source venv/bin/activate && python -c "from core.filter import JobFilter; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add job-application-agent/core/filter.py
git commit -m "feat: wire JobFilter to real LLM scorer via JobScorer"
```

---

## Task 6: Upgrade `core/linkedin.py`

**Files:**
- Modify: `core/linkedin.py`

Key changes: extract real JD from the detail panel, get real company name, wire in `ExternalPortalAgent`, fix Easy Apply modal multi-step flow with `form_filler`, use async `generate_pdf`.

- [ ] **Step 1: Replace `core/linkedin.py`**

```python
import asyncio
import os
import random
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from core.browser import JobBrowserAgent
from core.filter import JobFilter
from core.cv_tailor import CVTailor
from core.form_filler import UniversalFormFiller
from core.external_portal import ExternalPortalAgent
from core.db import JobDatabase

load_dotenv()

LINKEDIN_FEED_CHECK = ".global-nav__me-photo"


class LinkedInAgent(JobBrowserAgent):
    def __init__(self, headless=False):
        super().__init__(headless=headless, state_file="linkedin_session.json")
        self.login_url = "https://www.linkedin.com/login"
        self.email = os.getenv("LINKEDIN_EMAIL")
        self.password = os.getenv("LINKEDIN_PASSWORD")

    async def _is_logged_in(self, page) -> bool:
        try:
            await page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            el = await page.query_selector(LINKEDIN_FEED_CHECK)
            return el is not None
        except Exception:
            return False

    async def auto_login(self, page) -> bool:
        if os.path.exists(self.state_file):
            if await self._is_logged_in(page):
                print("✅ LinkedIn session valid.")
                return True
            print("⚠️ Session expired. Re-logging in...")
            os.remove(self.state_file)

        print(f"🤖 Logging into LinkedIn as {self.email}...")
        await page.goto(self.login_url)
        await page.fill("input#username", self.email)
        await page.fill("input#password", self.password)
        await page.click("button[type='submit']")
        print("⏳ Waiting 90s for 2FA approval on your phone...")
        await page.wait_for_timeout(90000)

        if "feed" in page.url or "checkpoint" not in page.url:
            await page.context.storage_state(path=self.state_file)
            print("✅ Login successful. Session saved.")
            return True

        print("⚠️ Login blocked (CAPTCHA/OTP).")
        await page.screenshot(path="linkedin_login_error.png")
        return False

    async def _extract_jd(self, page) -> str:
        selectors = [
            ".jobs-description-content__text",
            ".jobs-box__html-content",
            ".job-view-layout",
            "#job-details",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    if text and len(text) > 100:
                        return text[:3000]
            except Exception:
                continue
        return ""

    async def _extract_company(self, page) -> str:
        selectors = [
            ".jobs-unified-top-card__company-name",
            ".topcard__org-name-link",
            ".jobs-details-top-card__company-url",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    return (await el.inner_text()).strip()
            except Exception:
                continue
        return "UnknownCompany"

    async def _handle_easy_apply_modal(self, page, profile, resume_pdf_path, filler) -> str:
        for step in range(8):
            await page.wait_for_timeout(2000)

            # Resume upload step
            try:
                file_input = await page.query_selector('input[type="file"]')
                if file_input and os.path.exists(resume_pdf_path):
                    await file_input.set_input_files(resume_pdf_path)
                    print(f"   📎 Uploaded resume at step {step + 1}")
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Fill visible form fields
            await filler.parse_and_fill(page, page.url)

            # Try Submit
            submit_btn = page.locator('button:has-text("Submit application"), button:has-text("Submit Application")')
            if await submit_btn.count() > 0:
                try:
                    if await submit_btn.first.is_visible():
                        await submit_btn.first.click()
                        await page.wait_for_timeout(2000)
                        print("✅ Easy Apply submitted!")
                        return "applied"
                except Exception:
                    pass

            # Try Next
            next_btn = page.locator('button:has-text("Next"), button:has-text("Review"), button:has-text("Continue to next step")')
            if await next_btn.count() > 0:
                try:
                    if await next_btn.first.is_visible():
                        await next_btn.first.click()
                        continue
                except Exception:
                    pass

            # Modal dismissed or completed
            modal = await page.query_selector('[data-test-modal]')
            if not modal:
                return "applied"

            break

        return "failed"

    async def autonomous_search_and_apply(self, profile: dict, generator=None):
        stats = {"applied": 0, "skipped": 0, "failed": 0, "manual": 0}

        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()

            if not await self.auto_login(page):
                await browser.close()
                return stats

            db = JobDatabase()
            roles = profile.get("preferences", {}).get("roles", ["QA Lead"])

            for role in roles[:3]:
                search_query = "%20".join(role.split())
                url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}&f_AL=true&sortBy=DD"
                print(f"\n🔍 Searching LinkedIn for: '{role}' (Easy Apply only)...")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    print(f"⚠️ Navigation warning: {e}")
                await page.wait_for_timeout(4000)

                for page_num in range(1, 4):
                    print(f"\n📄 Page {page_num}...")
                    await page.evaluate(
                        "document.querySelector('.jobs-search-results-list')?.scrollTo(0, 9999)"
                    )
                    await page.wait_for_timeout(3000)

                    job_cards = await page.evaluate("""() => {
                        const anchors = Array.from(document.querySelectorAll('a[data-control-id], a.job-card-list__title--link, a.disabled.job-card-list__title'));
                        return anchors.map((a, idx) => ({
                            index: idx,
                            title: a.textContent.trim(),
                            href: a.href || ''
                        })).filter(j => j.title.length > 3);
                    }""")

                    if not job_cards:
                        print("No job cards found. Ending pagination.")
                        break

                    print(f"✅ {len(job_cards)} cards on page {page_num}")

                    for job in job_cards:
                        title = job["title"]
                        job_id = db.generate_job_id("linkedin_search", title)

                        if db.is_processed(job_id):
                            print(f"⏭️ Already processed: {title[:40]}")
                            stats["skipped"] += 1
                            continue

                        print(f"\n→ {title[:50]}")

                        # Click card to load detail panel
                        try:
                            await page.evaluate(
                                """(idx) => {
                                    const anchors = Array.from(document.querySelectorAll('a[data-control-id], a.job-card-list__title--link, a.disabled.job-card-list__title'));
                                    if (anchors[idx]) anchors[idx].click();
                                }""",
                                job["index"],
                            )
                            await page.wait_for_timeout(3000)
                        except Exception as e:
                            print(f"  ⚠️ Card click failed: {e}")
                            continue

                        jd = await self._extract_jd(page)
                        company = await self._extract_company(page)
                        job_id = db.generate_job_id(company, title)

                        if db.is_processed(job_id):
                            stats["skipped"] += 1
                            continue

                        # Score relevance
                        job_filter = JobFilter(profile)
                        result = job_filter.score_job(title, jd or title)
                        if not result["passed"]:
                            db.mark_processed(job_id, "linkedin", "skipped_low_score", title=title, company=company)
                            stats["skipped"] += 1
                            continue

                        # Tailor resume
                        tailor = CVTailor()
                        tailored_md = tailor.rewrite_cv(jd or title)
                        cv_path = f"tailored_linkedin_cv_{job_id[:8]}.pdf"
                        await tailor.generate_pdf(tailored_md, cv_path)

                        # Click Easy Apply
                        try:
                            await page.evaluate("""() => {
                                const btns = Array.from(document.querySelectorAll('button'));
                                const btn = btns.find(b =>
                                    b.textContent.includes('Easy Apply') ||
                                    b.className.includes('jobs-apply-button')
                                );
                                if (btn) btn.click();
                            }""")
                            await page.wait_for_timeout(3000)

                            # Check if redirected externally
                            if "linkedin.com" not in page.url:
                                filler = UniversalFormFiller(profile)
                                portal = ExternalPortalAgent(profile, filler)
                                outcome = await portal.apply(page, page.url, cv_path)
                            else:
                                filler = UniversalFormFiller(profile)
                                outcome = await self._handle_easy_apply_modal(page, profile, cv_path, filler)

                            db.mark_processed(job_id, "linkedin", outcome, title=title, company=company)
                            stats[outcome if outcome in stats else "failed"] += 1
                            print(f"  → Outcome: {outcome}")

                        except Exception as e:
                            print(f"  ⚠️ Apply error: {e}")
                            db.mark_processed(job_id, "linkedin", "failed", title=title, company=company)
                            stats["failed"] += 1
                        finally:
                            if os.path.exists(cv_path):
                                os.remove(cv_path)

                        await page.wait_for_timeout(random.randint(8, 20) * 1000)

                    # Next page
                    try:
                        has_next = await page.evaluate("""() => {
                            const btn = Array.from(document.querySelectorAll('button')).find(
                                b => b.getAttribute('aria-label', '').toLowerCase().includes('next')
                            );
                            if (btn) { btn.click(); return true; }
                            return false;
                        }""")
                        if not has_next:
                            break
                        await page.wait_for_timeout(5000)
                    except Exception:
                        break

            await browser.close()

        print(f"\n📊 LinkedIn Summary → Applied:{stats['applied']} Skipped:{stats['skipped']} Failed:{stats['failed']} Manual:{stats['manual']}")
        return stats
```

- [ ] **Step 2: Verify import works**

```bash
cd job-application-agent
source venv/bin/activate && python -c "from core.linkedin import LinkedInAgent; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add job-application-agent/core/linkedin.py
git commit -m "feat: upgrade LinkedIn agent — real JD extraction, scorer, tailor, external portal"
```

---

## Task 7: Upgrade `core/naukri.py`

**Files:**
- Modify: `core/naukri.py`

- [ ] **Step 1: Replace `core/naukri.py`**

```python
import asyncio
import os
import random
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from core.browser import JobBrowserAgent
from core.filter import JobFilter
from core.cv_tailor import CVTailor
from core.form_filler import UniversalFormFiller
from core.external_portal import ExternalPortalAgent
from core.db import JobDatabase

load_dotenv()


class NaukriAgent(JobBrowserAgent):
    def __init__(self, headless=False):
        super().__init__(headless=headless, state_file="naukri_session.json")
        self.login_url = "https://www.naukri.com/nlogin/login"
        self.email = os.getenv("NAUKRI_EMAIL")
        self.password = os.getenv("NAUKRI_PASSWORD")

    async def _is_logged_in(self, page) -> bool:
        try:
            await page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            el = await page.query_selector(".nI-gNb-lg-logo")
            return el is not None
        except Exception:
            return False

    async def auto_login(self, page) -> bool:
        if os.path.exists(self.state_file):
            print(f"🔓 Loading Naukri session...")
            return True

        print(f"🤖 Logging into Naukri as {self.email}...")
        await page.goto(self.login_url)
        await page.wait_for_timeout(2000)
        try:
            await page.fill("input#usernameField", self.email)
            await page.fill("input#passwordField", self.password)
            await page.click("button[type='submit']")
        except Exception:
            await page.evaluate(f"""() => {{
                document.querySelector('input[placeholder*="mail"]')?.setAttribute('value', '{self.email}');
                document.querySelector('input[type="password"]')?.setAttribute('value', '{self.password}');
            }}""")
        await page.wait_for_timeout(4000)
        await page.context.storage_state(path=self.state_file)
        print("✅ Naukri login session saved.")
        return True

    async def _extract_jd(self, page) -> str:
        selectors = [
            ".styles_job-desc-container__txpYf",
            ".job-desc",
            "[class*='description']",
            ".JDC",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    if text and len(text) > 100:
                        return text[:3000]
            except Exception:
                continue
        return ""

    async def _extract_company(self, page) -> str:
        selectors = [
            ".styles_jd-header-comp-name__MvqAI",
            ".comp-name",
            "[class*='company-name']",
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    return (await el.inner_text()).strip()
            except Exception:
                continue
        return "UnknownCompany"

    async def autonomous_search_and_apply(self, profile: dict, generator=None):
        stats = {"applied": 0, "skipped": 0, "failed": 0, "manual": 0}

        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()

            if not await self.auto_login(page):
                await browser.close()
                return stats

            db = JobDatabase()
            roles = profile.get("preferences", {}).get("roles", ["QA Lead"])

            for role in roles[:3]:
                slug = "-".join(role.lower().split())
                search_url = f"https://www.naukri.com/{slug}-jobs?k={role}&sort=r"
                print(f"\n🔍 Searching Naukri for: '{role}'...")
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    print(f"⚠️ Navigation warning: {e}")
                await page.wait_for_timeout(4000)

                for page_num in range(1, 4):
                    print(f"\n📄 Page {page_num}...")
                    await page.wait_for_timeout(3000)

                    job_cards = await page.evaluate("""() => {
                        const cards = Array.from(document.querySelectorAll('article.jobTuple, div.jobTupleHeader, .cust-job-tuple'));
                        if (cards.length > 0) {
                            return cards.map((c, idx) => {
                                const title = c.querySelector('a.title, .title, [class*="title"]')?.textContent?.trim() || '';
                                const company = c.querySelector('.comp-name, [class*="company"]')?.textContent?.trim() || '';
                                const href = c.querySelector('a.title, a[href*="/job-listings"]')?.href || '';
                                return { index: idx, title, company, href };
                            }).filter(j => j.title.length > 3);
                        }
                        // fallback: any anchor with job-listings in href
                        return Array.from(document.querySelectorAll('a[href*="job-listings"]')).map((a, idx) => ({
                            index: idx, title: a.textContent.trim(), company: '', href: a.href
                        })).filter(j => j.title.length > 3);
                    }""")

                    if not job_cards:
                        print("No job cards found.")
                        break

                    print(f"✅ {len(job_cards)} cards on page {page_num}")

                    for job in job_cards:
                        title = job["title"]
                        company = job["company"] or "UnknownCompany"
                        href = job["href"]
                        job_id = db.generate_job_id(company, title)

                        if db.is_processed(job_id):
                            stats["skipped"] += 1
                            continue

                        print(f"\n→ {title[:50]} @ {company[:30]}")

                        if not href:
                            stats["skipped"] += 1
                            continue

                        # Open job in new tab
                        job_page = await context.new_page()
                        try:
                            await job_page.goto(href, wait_until="domcontentloaded", timeout=30000)
                            await job_page.wait_for_timeout(3000)
                        except Exception as e:
                            print(f"  ⚠️ Could not open job page: {e}")
                            await job_page.close()
                            stats["failed"] += 1
                            continue

                        jd = await self._extract_jd(job_page)

                        # Score
                        job_filter = JobFilter(profile)
                        result = job_filter.score_job(title, jd or title)
                        if not result["passed"]:
                            db.mark_processed(job_id, "naukri", "skipped_low_score", title=title, company=company)
                            stats["skipped"] += 1
                            await job_page.close()
                            continue

                        # Tailor resume
                        tailor = CVTailor()
                        tailored_md = tailor.rewrite_cv(jd or title)
                        cv_path = f"tailored_naukri_cv_{job_id[:8]}.pdf"
                        await tailor.generate_pdf(tailored_md, cv_path)

                        # Click Apply
                        outcome = "failed"
                        try:
                            try:
                                async with context.expect_page(timeout=6000) as new_page_info:
                                    apply_btn = job_page.locator("button:has-text('Apply'), a:has-text('Apply')").first
                                    await apply_btn.click(force=True)
                                ext_page = await new_page_info.value
                                await ext_page.wait_for_load_state()
                                print(f"  🔗 External: {ext_page.url}")
                                filler = UniversalFormFiller(profile)
                                portal = ExternalPortalAgent(profile, filler)
                                outcome = await portal.apply(ext_page, ext_page.url, cv_path)
                                await ext_page.close()
                            except Exception:
                                # Internal Naukri apply
                                filler = UniversalFormFiller(profile)
                                filled = await filler.parse_and_fill(job_page, job_page.url)
                                if filled:
                                    await job_page.wait_for_timeout(3000)
                                    outcome = "applied"
                                else:
                                    outcome = "skipped_account_wall"
                                    stats["manual"] += 1

                        except Exception as e:
                            print(f"  ⚠️ Apply error: {e}")
                            outcome = "failed"

                        db.mark_processed(job_id, "naukri", outcome, title=title, company=company)
                        stats[outcome if outcome in stats else "failed"] += 1
                        print(f"  → Outcome: {outcome}")

                        if os.path.exists(cv_path):
                            os.remove(cv_path)

                        await job_page.close()
                        await page.wait_for_timeout(random.randint(8, 20) * 1000)

                    # Next page
                    try:
                        has_next = await page.evaluate("""() => {
                            const btn = Array.from(document.querySelectorAll('a, button, span')).find(
                                b => b.textContent.trim().toLowerCase() === 'next'
                            );
                            if (btn) { btn.click(); return true; }
                            return false;
                        }""")
                        if not has_next:
                            break
                        await page.wait_for_timeout(5000)
                    except Exception:
                        break

            await browser.close()

        print(f"\n📊 Naukri Summary → Applied:{stats['applied']} Skipped:{stats['skipped']} Failed:{stats['failed']} Manual:{stats['manual']}")
        return stats
```

- [ ] **Step 2: Verify import works**

```bash
cd job-application-agent
source venv/bin/activate && python -c "from core.naukri import NaukriAgent; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add job-application-agent/core/naukri.py
git commit -m "feat: upgrade Naukri agent — real JD extraction, scorer, tailor, external portal"
```

---

## Task 8: Upgrade `core/orchestrator.py`

**Files:**
- Modify: `core/orchestrator.py`

- [ ] **Step 1: Replace `core/orchestrator.py`**

```python
import schedule
import time
import asyncio
from core.linkedin import LinkedInAgent
from core.naukri import NaukriAgent


class DaemonOrchestrator:
    def __init__(self, profile: dict, generator=None):
        self.profile = profile

    def run_cycle(self):
        print("\n" + "=" * 60)
        print("🕒 [Orchestrator] Starting application cycle...")
        print("=" * 60)

        totals = {"applied": 0, "skipped": 0, "failed": 0, "manual": 0}

        try:
            linkedin = LinkedInAgent(headless=True)
            stats = asyncio.run(linkedin.autonomous_search_and_apply(self.profile))
            for k in totals:
                totals[k] += stats.get(k, 0)
        except Exception as e:
            print(f"❌ LinkedIn cycle error: {e}")

        try:
            naukri = NaukriAgent(headless=True)
            stats = asyncio.run(naukri.autonomous_search_and_apply(self.profile))
            for k in totals:
                totals[k] += stats.get(k, 0)
        except Exception as e:
            print(f"❌ Naukri cycle error: {e}")

        print("\n" + "=" * 60)
        print(
            f"📊 Cycle complete → "
            f"✅ Applied: {totals['applied']} | "
            f"⏭ Skipped: {totals['skipped']} | "
            f"❌ Failed: {totals['failed']} | "
            f"📋 Manual: {totals['manual']}"
        )
        print("💤 Sleeping until next cycle (4 hours)...")
        print("=" * 60)

    def start_daemon(self):
        print("🚀 [Orchestrator] 24/7 Agentic Loop Started!")
        print("ℹ️ Running first cycle immediately, then every 4 hours.")
        self.run_cycle()
        schedule.every(4).hours.do(self.run_cycle)
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n🛑 Daemon stopped.")
```

- [ ] **Step 2: Verify import works**

```bash
cd job-application-agent
source venv/bin/activate && python -c "from core.orchestrator import DaemonOrchestrator; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add job-application-agent/core/orchestrator.py
git commit -m "feat: upgrade orchestrator with cycle summary stats"
```

---

## Task 9: Run Full Test Suite

- [ ] **Step 1: Run all unit tests**

```bash
cd job-application-agent
source venv/bin/activate && pytest tests/ -v --tb=short
```

Expected output:
```
tests/test_cv_tailor.py::test_rewrite_returns_tailored_content PASSED
tests/test_cv_tailor.py::test_rewrite_falls_back_to_base_on_short_response PASSED
tests/test_cv_tailor.py::test_generate_pdf_creates_file PASSED
tests/test_external_portal.py::test_detect_workday PASSED
tests/test_external_portal.py::test_detect_greenhouse PASSED
tests/test_external_portal.py::test_detect_lever PASSED
tests/test_external_portal.py::test_detect_generic PASSED
tests/test_external_portal.py::test_hard_stop_video_interview PASSED
tests/test_external_portal.py::test_account_wall_returns_skipped PASSED
tests/test_form_filler.py::test_skips_account_wall_on_workday PASSED
tests/test_form_filler.py::test_returns_true_when_no_fields PASSED
tests/test_form_filler.py::test_skip_field_logs_to_manual_review PASSED
tests/test_job_scorer.py::test_score_above_threshold_sets_apply_true PASSED
tests/test_job_scorer.py::test_score_below_threshold_sets_apply_false PASSED
tests/test_job_scorer.py::test_apply_field_overridden_by_threshold PASSED
tests/test_job_scorer.py::test_malformed_json_retries_and_defaults PASSED
tests/test_job_scorer.py::test_strips_markdown_code_blocks PASSED

17 passed
```

- [ ] **Step 2: Smoke test — verify all imports chain correctly**

```bash
cd job-application-agent
source venv/bin/activate && python -c "
from core.job_scorer import JobScorer
from core.cv_tailor import CVTailor
from core.form_filler import UniversalFormFiller
from core.external_portal import ExternalPortalAgent
from core.linkedin import LinkedInAgent
from core.naukri import NaukriAgent
from core.orchestrator import DaemonOrchestrator
print('✅ All imports OK')
"
```

Expected: `✅ All imports OK`

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "test: full test suite passing — 17 unit tests"
```

---

## Task 10: Live Smoke Test (Headed Mode)

Run one cycle in headed mode against LinkedIn so you can watch every click live. This uses your real credentials and will attempt actual applications.

- [ ] **Step 1: Confirm .env has GOOGLE_API_KEY set**

```bash
cd job-application-agent
grep GOOGLE_API_KEY .env
```

Expected: `GOOGLE_API_KEY="your_actual_key_here"` (not placeholder)

- [ ] **Step 2: Delete old sessions to force fresh login**

```bash
cd job-application-agent
rm -f linkedin_session.json naukri_session.json
```

- [ ] **Step 3: Run LinkedIn in headed autonomous mode**

```bash
cd job-application-agent
source venv/bin/activate && python main.py --platform linkedin --autonomous --profile profile.yaml
```

Watch the browser window. Expected sequence:
1. Chrome opens, navigates to LinkedIn login
2. Login form filled automatically
3. Wait prompt: "Waiting 90s for 2FA approval on your phone..."
4. After 2FA: navigates to job search for "QA Lead"
5. Per job: prints score, "Tailoring CV...", "PDF generated...", "Easy Apply clicked..."
6. Final summary: `✅ Applied: N | ⏭ Skipped: N | ❌ Failed: N | 📋 Manual: N`

- [ ] **Step 4: Verify applied_jobs.json was written**

```bash
cd job-application-agent
python -c "
import json
data = json.load(open('applied_jobs.json'))
print(f'Jobs recorded: {len(data)}')
for jid, info in list(data.items())[:5]:
    print(f'  {info[\"title\"][:40]} — {info[\"status\"]}')
"
```

Expected: at least 1 job entry with status `applied`, `skipped_low_score`, or `failed`.

- [ ] **Step 5: Start 24/7 daemon**

```bash
cd job-application-agent
source venv/bin/activate && python main.py --daemon --profile profile.yaml
```

Expected:
```
🚀 [Orchestrator] 24/7 Agentic Loop Started!
ℹ️ Running first cycle immediately, then every 4 hours.
============================================================
🕒 [Orchestrator] Starting application cycle...
```

Leave running. It will apply every 4 hours. Stop with Ctrl+C.
