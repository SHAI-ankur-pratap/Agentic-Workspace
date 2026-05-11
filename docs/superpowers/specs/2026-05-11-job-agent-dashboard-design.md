# Job Agent Dashboard — Design Spec
**Date:** 2026-05-11  
**Status:** Approved  
**Scope:** A local Flask web dashboard for the job-application-agent that shows all agent activity — applied jobs with links, follow-ups, manual reviews, and skipped jobs — in a tab-based UI.

---

## 1. Problem

The agent writes outcomes to `applied_jobs.json` but there is no way to see what was applied to, which jobs need following up, or which need manual action without opening a raw JSON file. The candidate needs a visual report with clickable job links.

---

## 2. Architecture

```
job-application-agent/
├── dashboard.py               (NEW — Flask app, single file)
├── templates/
│   └── dashboard.html         (NEW — Jinja2 template, all tabs)
├── core/
│   └── db.py                  (UPGRADE — store url, applied_at, score per job)
└── applied_jobs.json          (UPGRADED schema — adds url, applied_at, score, pinned)
```

**Run:** `python dashboard.py` → open `http://localhost:5000`  
**No build step.** Flask + Jinja2 only. Same venv as the agent.

---

## 3. Data Model Upgrade (`applied_jobs.json`)

Current schema per record:
```json
{"platform": "linkedin", "status": "Applied", "title": "QA Lead", "company": ""}
```

New schema:
```json
{
  "platform": "linkedin",
  "status": "applied",
  "title": "QA Lead",
  "company": "Infosys",
  "url": "https://www.linkedin.com/jobs/view/...",
  "applied_at": "2026-05-11T22:30:00",
  "score": 9,
  "pinned": false
}
```

**New fields:**
- `url` — job posting URL (clickable "View Job ↗" link)
- `applied_at` — ISO timestamp of when agent processed the job
- `score` — Gemini relevance score (0–10), shown on Skipped tab
- `pinned` — boolean, true when user manually marks for follow-up

**Backward compatibility:** `db.py` fills missing fields with defaults on read so old records don't break.

`db.mark_processed()` signature extended:
```python
def mark_processed(self, job_id, platform, status, title="", company="", url="", score=None)
```

---

## 4. Dashboard (`dashboard.py` + `templates/dashboard.html`)

### Flask routes

| Route | Method | Description |
|---|---|---|
| `GET /` | GET | Render dashboard with all tab data |
| `POST /pin/<job_id>` | POST | Toggle `pinned=True` on a job record |
| `POST /unpin/<job_id>` | POST | Toggle `pinned=False` on a job record |

All three routes redirect back to `/#tab-followup` or `/#tab-applied` after action. No JSON API needed — standard HTML form POST.

### Tab definitions

| Tab | Contents | Status filter |
|---|---|---|
| Overview | Stats cards + progress bar + recent 5 activity items | all |
| Applied | All successfully applied jobs, searchable | `applied` |
| Follow-up | Auto (applied_at ≥ 7 days ago) + manually pinned | `applied` + age OR `pinned=true` |
| Manual | Jobs agent couldn't apply to automatically | `skipped_account_wall`, `skipped_hard_stop`, `failed` |
| Skipped | Jobs AI scored below 6/10 or duplicates | `skipped_low_score` |

### Overview tab

- **Stats cards:** Applied, Follow-up, Failed, Manual, Skipped, Total processed
- **Applied rate:** `applied / total_processed * 100`  
- **Last cycle info:** reads last modified time of `applied_jobs.json` as proxy for last run
- **Recent activity:** 5 most recent records by `applied_at` descending

### Applied tab

- Search bar filters by title or company (client-side JS, no server round-trip)
- Each card: `Title @ Company | Platform badge | Date | View Job ↗ | 📌 Mark Follow-up button`
- "Mark Follow-up" submits POST `/pin/<job_id>` → refreshes page

### Follow-up tab

- Info banner explaining auto vs pinned
- Auto entries: `applied_at` ≥ 7 days ago — show `⏰ auto · N days` badge
- Pinned entries: `pinned=True` — show `📌 pinned` badge
- Each card has "✕ Remove" / "✕ Unpin" button → POST `/unpin/<job_id>`
- "View Job ↗" link to original posting

### Manual tab

- Info banner explaining these need human action
- Each card: reason (e.g. "Account creation required (Workday)") + "Apply Manually ↗" link
- Sourced from `manual_review.txt` as well as DB records with manual status codes

### Skipped tab

- Each card: title + score badge (e.g. "Score 3/10 — junior role") + date
- No link (agent never opened the job page for low-score skips)

---

## 5. Visual Design

- **Colour system:**
  - Green border / badge → applied
  - Orange border / badge → follow-up / auto-flag
  - Purple border / badge → pinned
  - Red border / badge → failed / manual
  - Grey border / badge → skipped
- **Top bar:** dark (`#0f2027`), agent name + last cycle time + daemon status dot
- **Tabs:** white background, blue underline on active tab, count badges
- **Cards:** white, `box-shadow`, coloured left border (4px), flat button for actions
- **No external CSS frameworks** — inline styles in template only

---

## 6. `db.py` changes

- `mark_processed()` accepts `url=""` and `score=None` kwargs (defaults preserve backward compat)
- `get_all()` method returns full dict, filling missing keys with defaults
- `toggle_pin(job_id)` method sets `pinned = not current_pinned` and saves

---

## 7. Agent changes (`linkedin.py`, `naukri.py`)

Pass `url` and `score` when recording each job:

```python
# After extracting JD and scoring:
db.mark_processed(job_id, "linkedin", outcome, title=title, company=company, url=job_url, score=score_result["score"])
```

`job_url` is the URL of the job detail page, captured before applying.

---

## 8. Dependencies

```
flask          # add to requirements.txt
```

No other additions. Flask is the only new dependency.

---

## 9. Out of Scope

- Authentication / login to the dashboard (local tool, no auth needed)
- Email/Slack notifications
- Editing profile.yaml from the dashboard
- Starting/stopping the daemon from the dashboard
- Pagination (all records shown, expected volume is hundreds not thousands)
