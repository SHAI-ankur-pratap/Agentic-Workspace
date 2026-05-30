# Job Agent Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Flask dashboard at `http://localhost:5000` that displays all agent job activity across 5 tabs — Applied, Follow-up, Manual, Skipped, and Overview — with clickable job links.

**Architecture:** A single `dashboard.py` Flask app reads `applied_jobs.json` directly and renders a Jinja2 template. `db.py` is extended with three new fields (`url`, `applied_at`, `score`, `pinned`) and two new methods (`get_all`, `toggle_pin`). The LinkedIn and Naukri agents are updated to pass job URL and score when recording each job.

**Tech Stack:** Python 3, Flask, Jinja2 (no frontend build step, no JS framework)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/db.py` | MODIFY | Add `url`, `applied_at`, `score`, `pinned` fields; add `get_all()` and `toggle_pin()` |
| `core/linkedin.py` | MODIFY | Capture job URL per card; pass `url` + `score` to `mark_processed` |
| `core/naukri.py` | MODIFY | Capture job URL per card; pass `url` + `score` to `mark_processed` |
| `dashboard.py` | CREATE | Flask app — routes for `/`, `/pin/<id>`, `/unpin/<id>` |
| `templates/dashboard.html` | CREATE | Full Jinja2 template — all 5 tabs, CSS inline |
| `requirements.txt` | MODIFY | Add `flask` |
| `tests/test_db_upgrade.py` | CREATE | Unit tests for new db methods |

**Working directory for all commands:** `job-application-agent/`
**All python commands:** `source venv/bin/activate && python ...`
**All pytest commands:** `source venv/bin/activate && python -m pytest ...`

---

## Task 0: Install Flask

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Install flask into venv**

```bash
cd job-application-agent
source venv/bin/activate && pip install flask -q
python -c "import flask; print('flask', flask.__version__)"
```

Expected: `flask 3.x.x`

- [ ] **Step 2: Add to requirements.txt**

Replace the contents of `requirements.txt`:

```
playwright==1.42.0
langchain
langchain-google-genai
python-dotenv
pydantic
pyyaml
schedule
markdown2
fpdf2
flask
```

- [ ] **Step 3: Commit**

```bash
git add job-application-agent/requirements.txt
git commit -m "chore: add flask to requirements"
```

---

## Task 1: Upgrade `core/db.py`

**Files:**
- Modify: `core/db.py`
- Create: `tests/test_db_upgrade.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_db_upgrade.py`:

```python
import json
import pytest
from pathlib import Path


def make_db(tmp_path):
    from core.db import JobDatabase
    return JobDatabase(db_file=str(tmp_path / "jobs.json"))


def test_mark_processed_stores_new_fields(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed(
        "abc123", "linkedin", "applied",
        title="QA Lead", company="Infosys",
        url="https://linkedin.com/jobs/view/123",
        score=9,
    )
    data = json.loads((tmp_path / "jobs.json").read_text())
    record = data["abc123"]
    assert record["url"] == "https://linkedin.com/jobs/view/123"
    assert record["score"] == 9
    assert record["pinned"] is False
    assert "applied_at" in record and len(record["applied_at"]) > 0


def test_get_all_fills_missing_fields(tmp_path):
    db_file = tmp_path / "jobs.json"
    db_file.write_text(json.dumps({
        "old123": {"platform": "naukri", "status": "Applied", "title": "QA Lead", "company": ""}
    }))
    from core.db import JobDatabase
    db = JobDatabase(db_file=str(db_file))
    all_jobs = db.get_all()
    record = all_jobs["old123"]
    assert record["url"] == ""
    assert record["applied_at"] == ""
    assert record["score"] is None
    assert record["pinned"] is False


def test_toggle_pin_sets_true(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    db.toggle_pin("job1", True)
    all_jobs = db.get_all()
    assert all_jobs["job1"]["pinned"] is True


def test_toggle_pin_sets_false(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    db.toggle_pin("job1", True)
    db.toggle_pin("job1", False)
    all_jobs = db.get_all()
    assert all_jobs["job1"]["pinned"] is False


def test_pin_preserved_on_re_mark(tmp_path):
    db = make_db(tmp_path)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    db.toggle_pin("job1", True)
    db.mark_processed("job1", "linkedin", "applied", title="QA Lead", company="X")
    all_jobs = db.get_all()
    assert all_jobs["job1"]["pinned"] is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_db_upgrade.py -v 2>&1 | tail -10
```

Expected: 5 failures (missing fields/methods)

- [ ] **Step 3: Replace `core/db.py`**

```python
import json
import os
import hashlib
from datetime import datetime


class JobDatabase:
    def __init__(self, db_file="applied_jobs.json"):
        self.db_file = db_file
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save(self):
        with open(self.db_file, "w") as f:
            json.dump(self.data, f, indent=4)

    def generate_job_id(self, company_name, job_title):
        raw_id = f"{company_name.lower().strip()}_{job_title.lower().strip()}"
        return hashlib.md5(raw_id.encode()).hexdigest()

    def is_processed(self, job_id):
        return job_id in self.data

    def mark_processed(self, job_id, platform, status, title="", company="", url="", score=None):
        existing_pinned = self.data.get(job_id, {}).get("pinned", False)
        self.data[job_id] = {
            "platform": platform,
            "status": status,
            "title": title,
            "company": company,
            "url": url,
            "applied_at": datetime.now().isoformat(),
            "score": score,
            "pinned": existing_pinned,
        }
        self._save()

    def get_all(self):
        result = {}
        for job_id, job in self.data.items():
            result[job_id] = {
                "platform": job.get("platform", ""),
                "status": job.get("status", ""),
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "applied_at": job.get("applied_at", ""),
                "score": job.get("score"),
                "pinned": job.get("pinned", False),
            }
        return result

    def toggle_pin(self, job_id, pinned: bool):
        if job_id in self.data:
            self.data[job_id]["pinned"] = pinned
            self._save()
```

- [ ] **Step 4: Run to verify tests pass**

```bash
source venv/bin/activate && python -m pytest tests/test_db_upgrade.py -v 2>&1 | tail -10
```

Expected: `5 passed`

- [ ] **Step 5: Run full test suite to check nothing broke**

```bash
source venv/bin/activate && python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: `22 passed`

- [ ] **Step 6: Commit**

```bash
git add job-application-agent/core/db.py job-application-agent/tests/test_db_upgrade.py
git commit -m "feat: upgrade db.py with url, applied_at, score, pinned fields and get_all/toggle_pin"
```

---

## Task 2: Pass URL + Score from LinkedIn and Naukri agents

**Files:**
- Modify: `core/linkedin.py`
- Modify: `core/naukri.py`

### LinkedIn

- [ ] **Step 1: Capture job URL in `autonomous_search_and_apply` and pass to `mark_processed`**

In `core/linkedin.py`, find the block where `job_cards` are iterated. The `href` is already in `job["href"]`. Store it and pass to all `mark_processed` calls.

Replace every `db.mark_processed(job_id, "linkedin", ...)` call in `autonomous_search_and_apply` with the version that includes `url` and `score`. Find the section starting at the job scoring block and make these changes:

```python
# After: job_id = db.generate_job_id(company, title)
job_url = job.get("href", "")

# After scoring:
job_filter = JobFilter(profile)
result = job_filter.score_job(title, jd or title)
job_score = result.get("score", 0)
if not result["passed"]:
    db.mark_processed(job_id, "linkedin", "skipped_low_score",
                      title=title, company=company, url=job_url, score=job_score)
    stats["skipped"] += 1
    continue

# After applying (replace all mark_processed calls in the apply block):
db.mark_processed(job_id, "linkedin", outcome,
                  title=title, company=company, url=job_url, score=job_score)
```

The full updated `autonomous_search_and_apply` inner loop (replace from `for job in job_cards:` down to the delay):

```python
                for job in job_cards:
                    title = job["title"]
                    job_url = job.get("href", "")
                    job_id = db.generate_job_id("linkedin_" + role, title)

                    if db.is_processed(job_id):
                        stats["skipped"] += 1
                        continue

                    print(f"\n  → {title[:55]}")

                    try:
                        await page.evaluate(
                            """(idx) => {
                                const a = Array.from(document.querySelectorAll(
                                    'a.job-card-list__title--link, a[class*="job-card-list__title"], a[class*="base-search-card__title"]'
                                ))[idx];
                                if (a) a.click();
                            }""",
                            job["index"],
                        )
                        await page.wait_for_timeout(3000)
                    except Exception as e:
                        print(f"  ⚠️ Card click: {e}")
                        continue

                    jd = await self._extract_jd(page)
                    company = await self._extract_company(page)
                    job_id = db.generate_job_id(company, title)

                    if db.is_processed(job_id):
                        stats["skipped"] += 1
                        continue

                    job_filter = JobFilter(profile)
                    result = job_filter.score_job(title, jd or title)
                    job_score = result.get("score", 0)
                    if not result["passed"]:
                        db.mark_processed(job_id, "linkedin", "skipped_low_score",
                                          title=title, company=company,
                                          url=job_url, score=job_score)
                        stats["skipped"] += 1
                        continue

                    tailor = CVTailor()
                    tailored_md = tailor.rewrite_cv(jd or title)
                    cv_path = f"tailored_linkedin_cv_{job_id[:8]}.pdf"
                    await tailor.generate_pdf(tailored_md, cv_path)

                    outcome = "failed"
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

                        if "linkedin.com" not in page.url:
                            filler = UniversalFormFiller(profile)
                            portal = ExternalPortalAgent(profile, filler)
                            outcome = await portal.apply(page, page.url, cv_path)
                        else:
                            filler = UniversalFormFiller(profile)
                            outcome = await self._handle_easy_apply_modal(
                                page, profile, cv_path, filler
                            )

                    except Exception as e:
                        print(f"  ⚠️ Apply error: {e}")
                        outcome = "failed"
                    finally:
                        if os.path.exists(cv_path):
                            os.remove(cv_path)

                    db.mark_processed(job_id, "linkedin", outcome,
                                      title=title, company=company,
                                      url=job_url, score=job_score)
                    stats[outcome if outcome in stats else "failed"] += 1
                    print(f"  → Outcome: {outcome}")

                    await page.wait_for_timeout(random.randint(8, 20) * 1000)
```

- [ ] **Step 2: Verify LinkedIn import still works**

```bash
source venv/bin/activate && python -c "from core.linkedin import LinkedInAgent; print('OK')"
```

Expected: `OK`

### Naukri

- [ ] **Step 3: Pass url + score in `core/naukri.py`**

In `autonomous_search_and_apply`, `href` is already in `job["href"]`. Replace every `db.mark_processed` call in the inner loop with the version that includes `url` and `score`. The updated inner loop:

```python
                for job in job_cards:
                    title = job["title"]
                    href = job["href"]
                    if not href:
                        continue

                    job_id = db.generate_job_id("naukri_" + role, title)
                    if db.is_processed(job_id):
                        stats["skipped"] += 1
                        continue

                    print(f"\n  → {title[:55]}")

                    job_page = await context.new_page()
                    try:
                        await job_page.goto(href, wait_until="domcontentloaded", timeout=30000)
                        await job_page.wait_for_timeout(3000)
                    except Exception as e:
                        print(f"  ⚠️ Page load: {e}")
                        await job_page.close()
                        stats["failed"] += 1
                        continue

                    jd = await self._extract_jd(job_page)
                    company = await self._extract_company(job_page)
                    job_id = db.generate_job_id(company, title)

                    if db.is_processed(job_id):
                        stats["skipped"] += 1
                        await job_page.close()
                        continue

                    job_filter = JobFilter(profile)
                    result = job_filter.score_job(title, jd or title)
                    job_score = result.get("score", 0)
                    if not result["passed"]:
                        db.mark_processed(job_id, "naukri", "skipped_low_score",
                                          title=title, company=company,
                                          url=href, score=job_score)
                        stats["skipped"] += 1
                        await job_page.close()
                        continue

                    tailor = CVTailor()
                    tailored_md = tailor.rewrite_cv(jd or title)
                    cv_path = f"tailored_naukri_cv_{job_id[:8]}.pdf"
                    await tailor.generate_pdf(tailored_md, cv_path)

                    outcome = "failed"
                    try:
                        try:
                            async with context.expect_page(timeout=6000) as new_page_info:
                                apply_btn = job_page.locator(
                                    "button:has-text('Apply'), a:has-text('Apply')"
                                ).first
                                await apply_btn.click(force=True)
                            ext_page = await new_page_info.value
                            await ext_page.wait_for_load_state()
                            print(f"  🔗 External: {ext_page.url}")
                            filler = UniversalFormFiller(profile)
                            portal = ExternalPortalAgent(profile, filler)
                            outcome = await portal.apply(ext_page, ext_page.url, cv_path)
                            await ext_page.close()
                        except Exception:
                            filler = UniversalFormFiller(profile)
                            filled = await filler.parse_and_fill(job_page, job_page.url)
                            outcome = "applied" if filled else "skipped_account_wall"
                            if not filled:
                                stats["manual"] += 1

                    except Exception as e:
                        print(f"  ⚠️ Apply error: {e}")
                        outcome = "failed"
                    finally:
                        if os.path.exists(cv_path):
                            os.remove(cv_path)

                    db.mark_processed(job_id, "naukri", outcome,
                                      title=title, company=company,
                                      url=href, score=job_score)
                    stats[outcome if outcome in stats else "failed"] += 1
                    print(f"  → Outcome: {outcome}")

                    await job_page.close()
                    await page.wait_for_timeout(random.randint(8, 20) * 1000)
```

- [ ] **Step 4: Verify Naukri import**

```bash
source venv/bin/activate && python -c "from core.naukri import NaukriAgent; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add job-application-agent/core/linkedin.py job-application-agent/core/naukri.py
git commit -m "feat: pass job url and score to db.mark_processed in linkedin and naukri agents"
```

---

## Task 3: Create `dashboard.py`

**Files:**
- Create: `dashboard.py`

- [ ] **Step 1: Create `dashboard.py`**

```python
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect
from core.db import JobDatabase

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "applied_jobs.json")
FOLLOWUP_DAYS = 7

MANUAL_STATUSES = {"skipped_account_wall", "skipped_hard_stop", "failed"}


def _parse_dt(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except Exception:
        return None


@app.route("/")
def index():
    db = JobDatabase(DB_PATH)
    jobs = db.get_all()
    now = datetime.now()
    cutoff = now - timedelta(days=FOLLOWUP_DAYS)

    applied, followups, manual, skipped = [], [], [], []

    for job_id, job in jobs.items():
        job["id"] = job_id
        status = job.get("status", "").lower()
        applied_at = _parse_dt(job.get("applied_at", ""))
        job["days_ago"] = (now - applied_at).days if applied_at else None

        if status == "applied":
            applied.append(job)
            is_old = applied_at and applied_at < cutoff
            if is_old or job.get("pinned"):
                followups.append(job)
        elif status in MANUAL_STATUSES:
            manual.append(job)
        elif status == "skipped_low_score":
            skipped.append(job)

    def sort_key(j):
        dt = _parse_dt(j.get("applied_at", ""))
        return dt or datetime.min

    applied.sort(key=sort_key, reverse=True)
    followups.sort(key=sort_key, reverse=True)
    recent = sorted(jobs.values(), key=sort_key, reverse=True)[:5]

    total = len(jobs)
    n_applied = len(applied)
    stats = {
        "applied": n_applied,
        "followup": len(followups),
        "manual": len(manual),
        "skipped": len(skipped),
        "failed": sum(1 for j in jobs.values() if j.get("status", "").lower() == "failed"),
        "total": total,
        "rate": round(n_applied / total * 100) if total else 0,
    }

    last_modified = None
    if os.path.exists(DB_PATH):
        ts = os.path.getmtime(DB_PATH)
        last_modified = datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M")

    return render_template(
        "dashboard.html",
        stats=stats,
        applied=applied,
        followups=followups,
        manual=manual,
        skipped=skipped,
        recent=recent,
        last_modified=last_modified,
    )


@app.route("/pin/<job_id>", methods=["POST"])
def pin(job_id):
    db = JobDatabase(DB_PATH)
    db.toggle_pin(job_id, True)
    return redirect("/#tab-followup")


@app.route("/unpin/<job_id>", methods=["POST"])
def unpin(job_id):
    db = JobDatabase(DB_PATH)
    db.toggle_pin(job_id, False)
    return redirect("/#tab-applied")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
source venv/bin/activate && python -c "import dashboard; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add job-application-agent/dashboard.py
git commit -m "feat: add Flask dashboard server"
```

---

## Task 4: Create `templates/dashboard.html`

**Files:**
- Create: `templates/dashboard.html`

- [ ] **Step 1: Create `templates/` directory**

```bash
mkdir -p job-application-agent/templates
```

- [ ] **Step 2: Create `templates/dashboard.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JobAgent Dashboard</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#222;font-size:13px}
a{color:#1976d2;text-decoration:none}
a:hover{text-decoration:underline}

.topbar{background:#0f2027;color:#fff;padding:12px 24px;display:flex;justify-content:space-between;align-items:center}
.topbar h1{font-size:17px;font-weight:600}
.topbar .meta{font-size:11px;color:#aaa}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#4caf50;margin-right:5px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

.tabs{background:#fff;border-bottom:1px solid #e0e0e0;padding:0 24px;display:flex;gap:0;overflow-x:auto}
.tab{padding:12px 18px;cursor:pointer;border-bottom:3px solid transparent;font-size:13px;color:#666;white-space:nowrap;user-select:none}
.tab.active{border-bottom-color:#1976d2;color:#1976d2;font-weight:600}
.tab:hover:not(.active){color:#333;background:#f8f8f8}
.cnt{background:#f0f0f0;color:#555;padding:1px 7px;border-radius:10px;font-size:10px;margin-left:5px;font-weight:600}
.cnt.green{background:#e8f5e9;color:#2e7d32}
.cnt.orange{background:#fff3e0;color:#e65100}
.cnt.red{background:#ffebee;color:#c62828}
.cnt.purple{background:#f3e5f5;color:#6a1b9a}

.content{padding:20px 24px;max-width:1000px}
.tab-panel{display:none}.tab-panel.active{display:block}

/* Stats */
.stats{display:flex;gap:12px;margin-bottom:18px;flex-wrap:wrap}
.stat{flex:1;min-width:120px;background:#fff;border-radius:8px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.stat .num{font-size:26px;font-weight:700;line-height:1}
.stat .lbl{font-size:11px;color:#888;margin-top:3px;text-transform:uppercase;letter-spacing:.4px}
.stat.green .num{color:#2e7d32}.stat.orange .num{color:#e65100}
.stat.red .num{color:#c62828}.stat.grey .num{color:#555}.stat.purple .num{color:#6a1b9a}

.prog-wrap{margin-bottom:18px}
.prog-bar{height:6px;background:#e0e0e0;border-radius:3px;overflow:hidden}
.prog-fill{height:100%;background:linear-gradient(90deg,#1976d2,#42a5f5);border-radius:3px}
.prog-label{font-size:11px;color:#888;margin-top:4px}

.cycle-info{background:#fff;border-radius:7px;padding:11px 14px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.07);font-size:12px;color:#555}
.cycle-info strong{color:#222}

.section-label{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;color:#999;margin-bottom:8px;margin-top:16px}

/* Job cards */
.job-card{background:#fff;border-radius:7px;padding:11px 14px;margin-bottom:7px;box-shadow:0 1px 3px rgba(0,0,0,.07);border-left:4px solid #4caf50;display:flex;justify-content:space-between;align-items:center;gap:10px}
.job-card.orange{border-left-color:#ff9800}
.job-card.red{border-left-color:#f44336}
.job-card.grey{border-left-color:#bdbdbd}
.job-card.purple{border-left-color:#9c27b0}
.job-card .left h4{font-size:13px;font-weight:600;margin-bottom:3px}
.job-card .left h4 span{color:#888;font-weight:400}
.job-card .meta{font-size:11px;color:#888;display:flex;gap:8px;align-items:center;flex-wrap:wrap}

.badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600}
.badge.li{background:#e3f2fd;color:#1565c0}
.badge.nk{background:#fce4ec;color:#c62828}
.badge.auto{background:#fff9c4;color:#8d6e00}
.badge.pinned{background:#ede7f6;color:#4527a0}
.badge.skipped{background:#f5f5f5;color:#757575}
.badge.reason{background:#ffebee;color:#c62828;max-width:300px;white-space:normal}

.pin-btn{background:#fff8e1;border:1px solid #ffc107;color:#e65100;border-radius:5px;padding:4px 10px;font-size:11px;cursor:pointer;white-space:nowrap;flex-shrink:0}
.pin-btn:hover{background:#ffecb3}
.unpin-btn{background:#fce4ec;border:1px solid #ef9a9a;color:#c62828;border-radius:5px;padding:4px 10px;font-size:11px;cursor:pointer;white-space:nowrap;flex-shrink:0}
.unpin-btn:hover{background:#ffcdd2}

.search-bar{background:#fff;border:1px solid #e0e0e0;border-radius:6px;padding:8px 12px;width:100%;margin-bottom:12px;font-size:13px;outline:none}
.search-bar:focus{border-color:#1976d2}

.info-banner{border-radius:6px;padding:10px 14px;margin-bottom:12px;font-size:12px}
.info-banner.yellow{background:#fff8e1;border:1px solid #ffe082;color:#7b5800}
.info-banner.red{background:#fce4ec;border:1px solid #f48fb1;color:#880e4f}
.info-banner.grey{background:#f5f5f5;border:1px solid #e0e0e0;color:#555}

.empty{text-align:center;color:#bbb;padding:40px;font-size:13px}
</style>
</head>
<body>

<div class="topbar">
  <h1>🤖 JobAgent Dashboard</h1>
  <div class="meta">
    <span class="dot"></span>
    {% if last_modified %}Last updated: {{ last_modified }}{% else %}No data yet{% endif %}
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('overview',this)">📊 Overview</div>
  <div class="tab" onclick="switchTab('applied',this)">✅ Applied <span class="cnt green">{{ stats.applied }}</span></div>
  <div class="tab" onclick="switchTab('followup',this)">📋 Follow-up <span class="cnt orange">{{ stats.followup }}</span></div>
  <div class="tab" onclick="switchTab('manual',this)">⚠️ Manual <span class="cnt red">{{ stats.manual }}</span></div>
  <div class="tab" onclick="switchTab('skipped',this)">⏭ Skipped <span class="cnt">{{ stats.skipped }}</span></div>
</div>

<div class="content">

  {# ── OVERVIEW ── #}
  <div class="tab-panel active" id="tab-overview">
    <div class="stats">
      <div class="stat green"><div class="num">{{ stats.applied }}</div><div class="lbl">Applied</div></div>
      <div class="stat orange"><div class="num">{{ stats.followup }}</div><div class="lbl">Follow-up</div></div>
      <div class="stat red"><div class="num">{{ stats.failed }}</div><div class="lbl">Failed</div></div>
      <div class="stat purple"><div class="num">{{ stats.manual }}</div><div class="lbl">Manual</div></div>
      <div class="stat grey"><div class="num">{{ stats.skipped }}</div><div class="lbl">Skipped</div></div>
      <div class="stat grey"><div class="num">{{ stats.total }}</div><div class="lbl">Total</div></div>
    </div>
    <div class="prog-wrap">
      <div class="prog-bar"><div class="prog-fill" style="width:{{ stats.rate }}%"></div></div>
      <div class="prog-label">Applied rate: {{ stats.rate }}% ({{ stats.applied }} of {{ stats.total }})</div>
    </div>
    {% if last_modified %}
    <div class="cycle-info">🕒 <strong>Last updated:</strong> {{ last_modified }}</div>
    {% endif %}
    <div class="section-label">Recent Activity</div>
    {% for job in recent %}
      {% set s = job.status | lower %}
      <div class="job-card {% if s == 'applied' %}green{% elif 'skip' in s %}grey{% else %}red{% endif %}">
        <div class="left">
          <h4>{{ job.title }} <span>{% if job.company %}@ {{ job.company }}{% endif %}</span></h4>
          <div class="meta">
            <span class="badge {% if job.platform == 'linkedin' %}li{% else %}nk{% endif %}">
              {{ job.platform | upper | truncate(2, True, '') }}
            </span>
            <span>{{ job.status }}</span>
            {% if job.applied_at %}<span>{{ job.applied_at[:10] }}</span>{% endif %}
            {% if job.url %}<a href="{{ job.url }}" target="_blank">View Job ↗</a>{% endif %}
          </div>
        </div>
      </div>
    {% else %}
      <div class="empty">No activity yet. Start the daemon to begin applying.</div>
    {% endfor %}
  </div>

  {# ── APPLIED ── #}
  <div class="tab-panel" id="tab-applied">
    <input class="search-bar" id="applied-search" placeholder="🔍  Search by title or company..." oninput="filterCards('applied-list', this.value)">
    <div id="applied-list">
    {% for job in applied %}
      <div class="job-card" data-search="{{ job.title | lower }} {{ job.company | lower }}">
        <div class="left">
          <h4>{{ job.title }} <span>{% if job.company %}@ {{ job.company }}{% endif %}</span></h4>
          <div class="meta">
            <span class="badge {% if job.platform == 'linkedin' %}li{% else %}nk{% endif %}">{{ job.platform | upper | truncate(2, True, '') }}</span>
            {% if job.applied_at %}<span>{{ job.applied_at[:10] }}</span>{% endif %}
            {% if job.url %}<a href="{{ job.url }}" target="_blank">View Job ↗</a>{% endif %}
          </div>
        </div>
        <form action="/pin/{{ job.id }}" method="post" style="margin:0">
          <button class="pin-btn" type="submit">📌 Mark Follow-up</button>
        </form>
      </div>
    {% else %}
      <div class="empty">No applied jobs yet.</div>
    {% endfor %}
    </div>
  </div>

  {# ── FOLLOW-UP ── #}
  <div class="tab-panel" id="tab-followup">
    <div class="info-banner yellow">
      ⏰ <strong>Auto-flagged</strong> = applied 7+ days ago &nbsp;·&nbsp; 📌 <strong>Pinned</strong> = manually marked by you
    </div>
    {% for job in followups %}
      {% set is_pinned = job.pinned %}
      <div class="job-card {% if is_pinned %}purple{% else %}orange{% endif %}">
        <div class="left">
          <h4>{{ job.title }} <span>{% if job.company %}@ {{ job.company }}{% endif %}</span></h4>
          <div class="meta">
            <span class="badge {% if job.platform == 'linkedin' %}li{% else %}nk{% endif %}">{{ job.platform | upper | truncate(2, True, '') }}</span>
            {% if is_pinned %}
              <span class="badge pinned">📌 pinned</span>
            {% elif job.days_ago is not none %}
              <span class="badge auto">⏰ auto · {{ job.days_ago }}d</span>
            {% endif %}
            {% if job.url %}<a href="{{ job.url }}" target="_blank">View Job ↗</a>{% endif %}
          </div>
        </div>
        <form action="/unpin/{{ job.id }}" method="post" style="margin:0">
          <button class="unpin-btn" type="submit">{% if is_pinned %}✕ Unpin{% else %}✕ Remove{% endif %}</button>
        </form>
      </div>
    {% else %}
      <div class="empty">No follow-ups yet. Jobs applied 7+ days ago will appear here automatically.</div>
    {% endfor %}
  </div>

  {# ── MANUAL ── #}
  <div class="tab-panel" id="tab-manual">
    <div class="info-banner red">
      ⚠️ The agent could not apply to these jobs automatically — they need your manual attention.
    </div>
    {% for job in manual %}
      <div class="job-card red">
        <div class="left">
          <h4>{{ job.title }} <span>{% if job.company %}@ {{ job.company }}{% endif %}</span></h4>
          <div class="meta">
            <span class="badge {% if job.platform == 'linkedin' %}li{% else %}nk{% endif %}">{{ job.platform | upper | truncate(2, True, '') }}</span>
            <span class="badge reason">{{ job.status | replace('_', ' ') | title }}</span>
            {% if job.url %}<a href="{{ job.url }}" target="_blank">Apply Manually ↗</a>{% endif %}
          </div>
        </div>
      </div>
    {% else %}
      <div class="empty">No manual review items.</div>
    {% endfor %}
  </div>

  {# ── SKIPPED ── #}
  <div class="tab-panel" id="tab-skipped">
    <div class="info-banner grey">
      These jobs were skipped by the AI scorer (score &lt; 6/10) or were already processed.
    </div>
    {% for job in skipped %}
      <div class="job-card grey">
        <div class="left">
          <h4>{{ job.title }} <span>{% if job.company %}@ {{ job.company }}{% endif %}</span></h4>
          <div class="meta">
            <span class="badge {% if job.platform == 'linkedin' %}li{% else %}nk{% endif %}">{{ job.platform | upper | truncate(2, True, '') }}</span>
            {% if job.score is not none %}
              <span class="badge skipped">Score {{ job.score }}/10</span>
            {% endif %}
            {% if job.applied_at %}<span>{{ job.applied_at[:10] }}</span>{% endif %}
          </div>
        </div>
      </div>
    {% else %}
      <div class="empty">No skipped jobs.</div>
    {% endfor %}
  </div>

</div>

<script>
function switchTab(name, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}
function filterCards(listId, query) {
  const q = query.toLowerCase();
  document.querySelectorAll('#' + listId + ' .job-card').forEach(card => {
    const text = card.dataset.search || '';
    card.style.display = text.includes(q) ? '' : 'none';
  });
}
// Restore tab from URL hash on load
window.addEventListener('load', () => {
  const hash = location.hash.replace('#', '');
  if (hash) {
    const el = document.querySelector(`.tab[onclick*="${hash.replace('tab-', '')}"]`);
    if (el) el.click();
  }
});
</script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add job-application-agent/templates/dashboard.html
git commit -m "feat: add dashboard Jinja2 template with 5 tabs"
```

---

## Task 5: Smoke Test — Run the Dashboard

- [ ] **Step 1: Run all unit tests**

```bash
cd job-application-agent
source venv/bin/activate && python -m pytest tests/ -v 2>&1 | tail -8
```

Expected: `22 passed`

- [ ] **Step 2: Start the dashboard**

```bash
source venv/bin/activate && python dashboard.py
```

Expected output:
```
 * Running on http://127.0.0.1:5000
 * Debug mode: on
```

- [ ] **Step 3: Open in browser and verify**

Open `http://localhost:5000` in your browser. Check:
- Overview tab loads with stats cards
- Applied tab shows job cards (from existing `applied_jobs.json`)
- Follow-up tab shows the info banner (may be empty if no 7-day-old records yet)
- Manual tab shows the info banner
- Skipped tab shows the info banner
- Tabs switch without page reload

- [ ] **Step 4: Test pin/unpin flow**

If there are applied jobs in the Applied tab:
1. Click "📌 Mark Follow-up" on any job
2. Verify page redirects to `/#tab-followup`
3. Verify the job appears in Follow-up with "📌 pinned" badge
4. Click "✕ Unpin" — verify it disappears from Follow-up tab

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: job agent dashboard — Flask app with 5-tab report, pin/unpin follow-ups"
```
