"""Run once to seed demo data for the delivery head demo."""
import secrets
import sys
from datetime import datetime, timedelta

from auth import hash_password
from database import SessionLocal
from models import (
    ExecutionResult, ExecutionRun, Project, ShareToken, TCIDSequence,
    TestCase, User,
)

DEMO_TEST_CASES = [
    ("Login with valid credentials", "1. Navigate to /login\n2. Enter valid email and password\n3. Click Sign In", "User redirected to dashboard, session cookie set", "P1"),
    ("Login with invalid password", "1. Navigate to /login\n2. Enter valid email, wrong password\n3. Click Sign In", "Error: 'Invalid credentials'. User stays on login page.", "P1"),
    ("Login — rate limited after 5 failures", "1. Attempt login with wrong password 6 times", "6th attempt returns 429 Too Many Requests", "P1"),
    ("Dashboard loads with job listings", "1. Log in as recruiter\n2. Navigate to dashboard", "Job listings visible, stats cards show correct counts", "P2"),
    ("Job listing — apply flow (naukri)", "1. Open a Naukri job listing\n2. Click Apply\n3. Complete application form", "Application submitted, confirmation shown in dashboard", "P1"),
    ("Job listing — apply flow (linkedin)", "1. Open a LinkedIn job listing\n2. Click Easy Apply\n3. Complete multi-step form", "Application submitted, status tracked in dashboard", "P1"),
    ("Candidate ranking — LLM score shown", "1. Import candidates for a job\n2. View ranking list", "Each candidate shows AI score 1-10 with reason", "P1"),
    ("Candidate ranking — filter by score", "1. Apply score filter >= 7\n2. View results", "Only candidates with score >= 7 shown", "P2"),
    ("Admin panel — view all jobs", "1. Log in as admin\n2. Navigate to /admin/jobs", "All jobs across all recruiters visible", "P2"),
    ("Admin panel — export candidates CSV", "1. Navigate to /admin/candidates\n2. Click Export CSV", "CSV downloaded with correct headers and all records", "P2"),
    ("API — POST /api/jobs returns 201", "1. POST /api/jobs with valid payload and auth token", "201 Created with job object in response", "P1"),
    ("API — GET /api/candidates pagination", "1. GET /api/candidates?page=1&limit=10", "10 candidates returned, total_count in response", "P2"),
    ("API — invalid API key returns 401", "1. Send request with invalid Bearer token", "401 Unauthorized, not 500", "P1"),
    ("LiteLLM proxy — generate cover letter", "1. POST /api/ai/cover-letter with job_id and candidate_id", "Cover letter generated within 15 seconds", "P2"),
    ("LiteLLM proxy — fallback on timeout", "1. Simulate LiteLLM timeout\n2. Attempt AI action", "503 returned with 'AI service unavailable, try again'", "P1"),
    ("Cloudflare Turnstile — blocks bot", "1. Submit application form without completing Turnstile challenge", "403 Forbidden, application not submitted", "P1"),
    ("Session storage — resume across tabs", "1. Open app in tab 1\n2. Log in\n3. Open tab 2", "Tab 2 shows authenticated state without re-login", "P2"),
    ("CSV import — valid file", "1. Navigate to Import\n2. Upload valid candidates.csv\n3. Click Import", "All rows imported, count shown in success message", "P1"),
    ("CSV import — missing required column", "1. Upload CSV missing 'email' column", "Error: 'Missing required column: email'", "P2"),
    ("Responsive — mobile job list", "1. Open dashboard on 375px viewport\n2. Scroll job list", "All jobs visible, no horizontal scroll, tap targets >= 44px", "P3"),
]


def seed():
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "admin@shorthills.ai").first():
            print("Already seeded. Skipping.")
            return

        # Users
        admin = User(email="admin@shorthills.ai", password_hash=hash_password("ShortHills@2024"),
                     full_name="Admin User", role="admin")
        qa = User(email="qa@shorthills.ai", password_hash=hash_password("ShortHills@2024"),
                  full_name="QA Lead", role="qa_lead")
        db.add_all([admin, qa])
        db.flush()
        print(f"Created users: {admin.email}, {qa.email}")

        # Project
        project = Project(name="Agentic Hiring Platform", client_name="Shorthills.ai",
                          description="AI-powered job application automation platform",
                          created_by=admin.id)
        db.add(project)
        db.flush()
        print(f"Created project: {project.name} ({project.id})")

        # TC-ID sequence
        seq = TCIDSequence(project_id=project.id, next_seq=1)
        db.add(seq)
        db.flush()

        # Test cases
        tcs = []
        for i, (title, steps, expected, priority) in enumerate(DEMO_TEST_CASES, 1):
            tc = TestCase(
                project_id=project.id, tc_id=f"TC-{i:03d}",
                title=title, steps=steps, expected_result=expected,
                priority=priority, status="active", component_tags=[],
                created_by=admin.id,
            )
            db.add(tc)
            tcs.append(tc)
        seq.next_seq = len(DEMO_TEST_CASES) + 1
        db.flush()
        print(f"Created {len(tcs)} test cases")

        # Completed run — Sprint 3
        run1 = ExecutionRun(
            project_id=project.id, name="Sprint 3 — QA Cycle",
            status="completed", is_live=True,
            executive_summary="Coverage improved 15% this sprint. All P1 issues from last report are resolved.",
            executive_summary_cached_at=datetime.utcnow(),
            created_by=qa.id,
        )
        db.add(run1)
        db.flush()

        statuses = (["pass"] * 16) + ["fail", "skip", "blocked"] + (["pass"] * (len(tcs) - 19))
        for tc, st in zip(tcs, statuses):
            db.add(ExecutionResult(run_id=run1.id, test_case_id=tc.id, status=st))

        # Share token for Sprint 3
        token = secrets.token_urlsafe(32)
        db.add(ShareToken(run_id=run1.id, token=token, expires_at=datetime.utcnow() + timedelta(days=30)))
        print(f"Sprint 3 share token: {token}")

        # In-progress run — Sprint 4
        run2 = ExecutionRun(
            project_id=project.id, name="Sprint 4 — In Progress",
            status="in_progress", is_live=True, created_by=qa.id,
        )
        db.add(run2)
        db.flush()

        for i, tc in enumerate(tcs[:11]):
            st = "pass" if i < 8 else "pending"
            db.add(ExecutionResult(run_id=run2.id, test_case_id=tc.id, status=st))
        for tc in tcs[11:]:
            db.add(ExecutionResult(run_id=run2.id, test_case_id=tc.id, status="pending"))

        db.commit()
        print("Demo seed complete.")
        print(f"  Admin login: admin@shorthills.ai / ShortHills@2024")
        print(f"  QA login:    qa@shorthills.ai / ShortHills@2024")
        print(f"  Project ID:  {project.id}")
        print(f"  Live portal: /reports/{token}")

    except Exception as e:
        db.rollback()
        print(f"Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
