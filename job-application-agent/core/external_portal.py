import os

PORTAL_PATTERNS = {
    "workday":         ["myworkdayjobs.com", "wd3.myworkdaysite.com", "wd1.myworkdaysite.com",
                        "wd5.myworkdaysite.com", "myworkday.com"],
    "greenhouse":      ["boards.greenhouse.io", "greenhouse.io/careers"],
    "lever":           ["jobs.lever.co", "hire.lever.co"],
    "smartrecruiters": ["jobs.smartrecruiters.com"],
    "ashby":           ["jobs.ashbyhq.com"],
    "rippling":        ["app.rippling.com/job-application"],
    "taleo":           ["taleo.net", "tbe.taleo.net"],
    "icims":           ["icims.com", "careers.icims.com"],
    "successfactors":  ["successfactors.com", "sap.com/careers"],
    "bamboohr":        ["bamboohr.com/jobs"],
    "jobvite":         ["jobs.jobvite.com", "hire.jobvite.com"],
    "workable":        ["apply.workable.com"],
}

HARD_STOP_PATTERNS = [
    "hirevue", "sparkhire",
    "video interview", "record a video response", "one-way video",
    "hackerrank", "codility", "testgorilla", "hackerearth",
]

# Phrases that indicate account creation is REQUIRED (no guest option visible)
ACCOUNT_WALL_PHRASES = [
    "sign in to apply", "sign up to apply", "register to apply",
    "please create an account to continue your application",
]

# Phrases where guest apply might still be possible
SOFT_ACCOUNT_PHRASES = [
    "create an account", "create account",
]

GUEST_APPLY_SELECTORS = [
    'a:has-text("Apply as Guest")',
    'button:has-text("Apply as Guest")',
    'a:has-text("Continue as Guest")',
    'button:has-text("Continue as Guest")',
    'a:has-text("Apply without account")',
    'a:has-text("Apply without signing in")',
    '[data-automation-id="createAccountLink"] + * a',
]

SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'button:has-text("Submit Application")',
    'button:has-text("Submit application")',
    'button:has-text("Submit")',
    'button:has-text("Send Application")',
    'button:has-text("Send My Application")',
    'button:has-text("Complete Application")',
    'button:has-text("Finish")',
    '[data-automation-id="bottom-navigation-next-button"]:has-text("Submit")',
    'input[type="submit"]',
]

NEXT_SELECTORS = [
    'button:has-text("Next")',
    'button:has-text("Continue")',
    'button:has-text("Proceed")',
    'button:has-text("Save and Continue")',
    'button:has-text("Save & Continue")',
    'button:has-text("Review")',
    'button:has-text("Review Application")',
    '[data-automation-id="bottom-navigation-next-button"]',
    'a:has-text("Next")',
    'a:has-text("Continue")',
]

CONFIRM_KEYWORDS = [
    "application submitted", "application received", "thank you for applying",
    "successfully applied", "your application has been", "we received your application",
    "application complete", "you've applied", "application was submitted",
    "thank you for your interest", "we'll be in touch",
]

COOKIE_DISMISS_SELECTORS = [
    'button:has-text("Accept")',
    'button:has-text("Accept All")',
    'button:has-text("I Agree")',
    'button:has-text("Got it")',
    'button:has-text("Allow all")',
    '#onetrust-accept-btn-handler',
    '.cookie-accept',
    '[data-cookiebanner="accept_button"]',
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
        print(f"🌐 [External Portal] Portal: {portal} — {page.url[:80]}")

        # Dismiss cookie banners first so they don't block form fields
        await self._dismiss_cookies(page)

        try:
            page_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
        except Exception:
            page_text = ""

        # Hard stops — no point trying (video interview, coding test etc.)
        for stop in HARD_STOP_PATTERNS:
            if stop in page_text or stop in page.url.lower():
                print(f"⛔ [External Portal] Hard stop detected: '{stop}'")
                self._log_manual_review(job_url, f"Hard stop: {stop}")
                return "skipped_hard_stop"

        # Hard account wall (no guest option on the page)
        if any(phrase in page_text for phrase in ACCOUNT_WALL_PHRASES):
            print("⛔ [External Portal] Hard account wall detected.")
            self._log_manual_review(job_url, "Account creation required (hard wall)")
            return "skipped_account_wall"

        # Soft account wall — try "Apply as Guest" first
        if any(phrase in page_text for phrase in SOFT_ACCOUNT_PHRASES):
            guest_clicked = await self._try_guest_apply(page)
            if not guest_clicked:
                print("⛔ [External Portal] Soft account wall — no guest option found.")
                self._log_manual_review(job_url, "Account creation required (no guest option)")
                return "skipped_account_wall"
            print("   ✅ Found and clicked 'Apply as Guest'")
            await page.wait_for_timeout(2000)

        resume_uploaded = False

        for step in range(8):
            print(f"   📋 [External Portal] Step {step + 1}...")
            await self._dismiss_cookies(page)

            # Upload resume once, on the first step that has a file input
            if not resume_uploaded:
                resume_uploaded = await self._upload_resume(page, resume_pdf_path)

            # Fill visible form fields via LLM
            filled = await self.form_filler.parse_and_fill(page, job_url)
            if not filled:
                # form_filler returned False = hard account wall inside the form
                return "skipped_account_wall"

            await page.wait_for_timeout(800)

            # Screenshot each step for debugging
            try:
                await page.screenshot(
                    path=f"debug_external_step{step + 1}.png"
                )
            except Exception:
                pass

            # Try Submit button
            if await self._try_submit(page):
                await page.wait_for_timeout(3000)
                try:
                    confirm = await page.evaluate(
                        "() => document.body.innerText.toLowerCase()"
                    )
                    if any(kw in confirm for kw in CONFIRM_KEYWORDS):
                        print("   ✅ [External Portal] Application confirmed submitted!")
                        return "applied"
                    print("   ✅ [External Portal] Submit clicked (no confirmation text).")
                    return "applied"
                except Exception:
                    return "applied"

            # Try Next / Continue
            if not await self._try_next(page):
                # Nothing to click — check if page says application is complete
                try:
                    confirm = await page.evaluate(
                        "() => document.body.innerText.toLowerCase()"
                    )
                    if any(kw in confirm for kw in CONFIRM_KEYWORDS):
                        print("   ✅ [External Portal] Application complete (detected from page text).")
                        return "applied"
                except Exception:
                    pass
                print("   ⚠️ [External Portal] No Next/Submit button found.")
                self._log_manual_review(job_url, "No submit/next button found after filling")
                return "failed"

            await page.wait_for_timeout(2000)

        self._log_manual_review(job_url, "Exceeded max steps (8)")
        return "failed"

    async def _dismiss_cookies(self, page):
        for sel in COOKIE_DISMISS_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                continue

    async def _try_guest_apply(self, page) -> bool:
        for sel in GUEST_APPLY_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    async def _upload_resume(self, page, resume_pdf_path: str) -> bool:
        if not resume_pdf_path or not os.path.exists(resume_pdf_path):
            return False
        try:
            # Try all file inputs — LinkedIn/Workday often have multiple hidden ones
            file_inputs = await page.query_selector_all('input[type="file"]')
            for fi in file_inputs:
                try:
                    if await fi.is_visible() or True:  # some are hidden but still work
                        await fi.set_input_files(resume_pdf_path)
                        print(f"   📎 Resume uploaded to portal")
                        await page.wait_for_timeout(1500)
                        return True
                except Exception:
                    continue
        except Exception as e:
            print(f"   ⚠️ Resume upload error: {e}")
        return False

    async def _try_submit(self, page) -> bool:
        for sel in SUBMIT_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible() and await btn.is_enabled():
                    print(f"   🚀 Clicking Submit...")
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    async def _try_next(self, page) -> bool:
        for sel in NEXT_SELECTORS:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible() and await btn.is_enabled():
                    text = await btn.inner_text()
                    print(f"   ➡️ Clicking '{text.strip()}'...")
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    def _log_manual_review(self, url: str, reason: str):
        with open(self.manual_review_file, "a") as f:
            f.write(f"[{reason}] {url}\n")
