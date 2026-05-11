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
                print("✅ [External Portal] Submitted (no confirmation text).")
                return "applied"

            if not await self._try_next(page):
                print("⚠️ [External Portal] No Next/Submit button found.")
                self._log_manual_review(job_url, "No submit/next button found")
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
