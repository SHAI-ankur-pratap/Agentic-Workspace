# Auto Job Application Agent — Design Spec
**Date:** 2026-05-11  
**Status:** Approved  
**Scope:** Upgrade existing `job-application-agent/` to a fully autonomous, LLM-powered agent that monitors LinkedIn and Naukri, tailors resumes per job, fills forms via AI, and handles external portals end-to-end.

---

## 1. Problem

The existing agent skeleton has working Playwright browser automation and a 4-hour daemon loop, but three critical pieces are mocked and non-functional:

- **CV tailoring** uses a string replace — no LLM rewrite
- **Form filling** uses hardcoded regex — no intelligent field mapping
- **External job links** (Workday, Greenhouse, Lever) are skipped entirely

The candidate provides credentials + resume once. The system handles everything else autonomously.

---

## 2. Architecture

```
job-application-agent/
├── main.py                    (entry point — CLI unchanged)
├── profile.yaml               (candidate config: roles, salary, QA bank)
├── base_resume.md             (master resume — source of truth)
├── .env                       (LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
│                               NAUKRI_EMAIL, NAUKRI_PASSWORD,
│                               GOOGLE_API_KEY)
├── applied_jobs.json          (deduplication store — JSON)
├── manual_review.txt          (jobs requiring human action)
│
└── core/
    ├── orchestrator.py        (daemon — 4h cycle, runs both platforms)
    ├── linkedin.py            (LinkedIn search + Easy Apply multi-step)
    ├── naukri.py              (Naukri search + apply flow)
    ├── external_portal.py     (NEW — Workday/Greenhouse/Lever/generic)
    ├── cv_tailor.py           (UPGRADED — Gemini LLM rewrite + weasyprint PDF)
    ├── form_filler.py         (UPGRADED — Gemini LLM field mapping)
    ├── job_scorer.py          (NEW — AI relevance scoring, threshold filter)
    ├── browser.py             (base browser — Playwright, stealth UA headers)
    ├── db.py                  (unchanged — JSON dedup store)
    └── filter.py              (upgraded — delegates to job_scorer)
```

### Execution flow per daemon cycle

```
Orchestrator wakes (every 4h)
  → LinkedIn agent
      → session reuse / re-login if expired
      → search each role from profile.yaml
      → per job card:
          → check DB (skip if already processed)
          → job_scorer → score < 6? log skipped_low_score, skip
          → cv_tailor → tailored_cv_{job_id}.pdf
          → apply_to_job()
              → LinkedIn Easy Apply (multi-step) OR
              → ExternalPortalAgent (redirect detected)
          → db.mark_processed(outcome)
          → delete tailored PDF
  → Naukri agent (same flow)
  → print cycle summary
  → sleep 4h
```

---

## 3. LLM Integration

**Model:** `gemini-1.5-flash` via `langchain-google-genai`  
**Cost:** Free tier — 1,500 requests/day, no credit card required  
**Key:** `GOOGLE_API_KEY` from [aistudio.google.com](https://aistudio.google.com)

### 3a. Job Scorer (`job_scorer.py`)

- **Input:** job title + description snippet + candidate profile dict
- **Output:** `{"score": 0-10, "reason": "...", "apply": true/false}`
- **Threshold:** score ≥ 6 → apply; below → `skipped_low_score`
- **Prompt checks:** seniority match, skill overlap, location fit, salary alignment
- **Retry:** malformed JSON → retry up to 2x → default `score=5` (apply) on persistent failure

### 3b. CV Tailor (`cv_tailor.py`)

- **Input:** `base_resume.md` + full job description
- **Output:** rewritten Markdown → compiled to PDF via `weasyprint`
- **Prompt instructions:**
  - Reorder bullets to lead with most-relevant experience
  - Swap in JD keywords naturally
  - Adjust summary line for the specific role
  - Do NOT fabricate experience (explicit instruction)
- **Validation:** output must contain candidate name + be >300 words; else fall back to base resume
- **PDF output:** `tailored_cv_{job_id}.pdf` (deleted after apply attempt)
- **PDF engine:** `markdown2` + `weasyprint` (replaces broken `fpdf` latin-1 approach)

### 3c. Form Filler (`form_filler.py`)

- **Input:** list of form fields `{label, type, options[]}` extracted from page + candidate profile
- **Output:** `{"field_name": "value_to_fill", ...}`
- **Profile QA bank** fed as few-shot examples (salary, notice, visa answers)
- **Low-confidence fields** (< 0.7 match): logged to `manual_review.txt`, not guessed
- **Covers:** text inputs, dropdowns, radio buttons, yes/no questions, file upload detection

---

## 4. External Portal Handling (`external_portal.py`)

Triggered when apply URL navigates away from LinkedIn/Naukri domain.

### Supported portals

| Portal | URL pattern | Strategy |
|---|---|---|
| Workday | `myworkdayjobs.com`, `wd3.myworkdaysite.com` | Multi-step form flow |
| Greenhouse | `boards.greenhouse.io` | Single-page form |
| Lever | `jobs.lever.co` | Single-page form |
| SmartRecruiters | `jobs.smartrecruiters.com` | Multi-step |
| Generic | anything else | Best-effort fill |

### Flow

1. Navigate to redirect URL (same browser context — cookies carry over)
2. Snapshot page — extract all visible form fields
3. LLM form fill via `form_filler.py`
4. Resume upload — detect `<input type="file">`, upload tailored PDF
5. Step through multi-step forms: click Next/Continue, LLM fills each step
6. Submit — click final Submit, wait for confirmation text
7. Log outcome

### Hard stops (always skip + log to `manual_review.txt`)

- Requires account creation (Workday SSO, Taleo login)
- Video interview required upfront (HireVue, Spark Hire)
- CAPTCHA not resolved within 5s
- Phone verification required

---

## 5. Data Flow & Error Handling

### Per-job pipeline

```
job card extracted
  → job_id = md5(company + title)
  → DB check → processed? skip
  → job_scorer → score < 6? log + skip
  → cv_tailor → tailored_cv_{job_id}.pdf
  → apply_to_job()
      → LinkedIn Easy Apply OR Naukri Apply OR ExternalPortalAgent
      → form_filler per step
  → outcome: applied | failed | manual_review | skipped_*
  → db.mark_processed(job_id, platform, outcome)
  → os.remove(tailored_cv_{job_id}.pdf)
```

### Error tiers

| Error | Action |
|---|---|
| Network timeout on job page | Retry once after 5s, then mark `failed` |
| LLM malformed JSON | Retry prompt up to 2x, then use profile defaults |
| LLM rate limit / network failure | Wait 30s, retry once, then skip job |
| Apply button not found | Screenshot → `debug_{job_id}.png`, mark `failed` |
| External portal: account wall | Log to `manual_review.txt`, mark `skipped_account_wall` |
| Unhandled exception | Log full traceback, continue to next job — daemon never crashes |

### Session management

- Sessions persist in `linkedin_session.json` / `naukri_session.json`
- Each cycle: load session → navigate to feed → check login state (profile avatar present)
- Expired session → re-run `auto_login()` → save new session
- LinkedIn 2FA: wait 90s for phone approval; on timeout → log `login_failed`, skip platform for this cycle

### Logging

- `agent_daemon.log` — all INFO output
- `agent_daemon_error.log` — errors + tracebacks
- `manual_review.txt` — URLs + reasons requiring human action
- Cycle summary printed: `✅ Applied: N | ⏭ Skipped: N | ❌ Failed: N | 📋 Manual: N`

---

## 6. Headed vs Headless Mode

| Flag | Mode | Use case |
|---|---|---|
| `--autonomous` | `headless=False` | Watch every click live, debug flows |
| `--daemon` | `headless=True` | Silent 24/7 background operation |

---

## 7. Candidate Setup (one-time)

1. Fill `profile.yaml` — roles, salary, QA bank answers
2. Write `base_resume.md` — master resume in Markdown
3. Set `.env`:
   ```
   LINKEDIN_EMAIL=...
   LINKEDIN_PASSWORD=...
   NAUKRI_EMAIL=...
   NAUKRI_PASSWORD=...
   GOOGLE_API_KEY=...   # free from aistudio.google.com
   ```
4. Run `pip install -r requirements.txt`
5. Run once with `--login` per platform to save sessions
6. Run `--daemon` to start the 24/7 loop

---

## 8. Dependencies (additions to requirements.txt)

```
# Existing (keep)
playwright==1.42.0
langchain
langchain-google-genai
python-dotenv
pydantic
pyyaml
schedule
markdown2

# Add
weasyprint          # PDF generation from Markdown (replaces fpdf)
```

---

## 9. Out of Scope

- Web dashboard / UI
- Email/SMS notifications
- Multiple candidate profiles simultaneously
- ATS parsing or application tracking beyond `applied_jobs.json`
- Glassdoor, Indeed, or other platforms (LinkedIn + Naukri only)
