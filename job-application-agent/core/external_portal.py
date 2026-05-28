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

    async def _handle_cloudflare(self, page, timeout_sec=60) -> bool:
        for i in range(timeout_sec // 2):
            try:
                title = await page.title()
                content = await page.content()
                is_cf = (
                    "just a moment" in title.lower() or 
                    "verify you are human" in content.lower() or 
                    "security verification" in content.lower() or
                    ("cloudflare" in content.lower() and "verify" in content.lower())
                )
                if is_cf:
                    if i % 5 == 0:
                        print(f"🚨 [Cloudflare Wall Detected] Please solve the challenge in the visible browser! (Waiting... {timeout_sec - i*2}s remaining)")
                    await page.wait_for_timeout(2000)
                else:
                    if i > 0:
                        print("✅ [Cloudflare Bypass] Challenge solved or bypassed! Continuing...")
                    return True
            except Exception as e:
                # Page might be navigating or reloading
                await page.wait_for_timeout(2000)
        return False

    async def resolve_redirects(self, page) -> bool:
        import urllib.parse
        initial_url = page.url
        initial_domain = urllib.parse.urlparse(initial_url).netloc
        
        print(f"🔄 [External Portal] Resolving potential redirects for {initial_url}...")
        
        # Handle Cloudflare first
        await self._handle_cloudflare(page)
        
        # 1. Dismiss cookies first
        await self._dismiss_cookies(page)

        # Wait for any apply button/link to appear
        try:
            print("   ⏳ [External Portal] Waiting for Apply button to appear...")
            await page.wait_for_selector(
                'a:has-text("Apply"), button:has-text("Apply"), a:has-text("apply"), button:has-text("apply"), a:has-text("position"), button:has-text("position")',
                timeout=5000
            )
            print("   ✅ [External Portal] Apply button detected.")
        except Exception:
            print("   ⚠️ [External Portal] Apply button wait timed out.")
        
        # 2. Look for any visible links/buttons with apply text
        # Let's search all <a> tags first
        links = await page.query_selector_all('a')
        best_href = None
        
        texts_to_check = [
            "apply for this position",
            "apply to this job",
            "apply on company site",
            "apply on company website",
            "apply to this remote job",
            "apply now",
            "apply"
        ]
        
        for text_pat in texts_to_check:
            for link in links:
                try:
                    if not await link.is_visible():
                        continue
                    text = (await link.inner_text()).lower().strip()
                    if text_pat in text:
                        href = await link.get_attribute("href")
                        if href:
                            href_lower = href.lower().strip()
                            if href_lower.startswith("http") or href_lower.startswith("//"):
                                # Check if it goes to a different domain
                                parsed_href = urllib.parse.urlparse(href)
                                if parsed_href.netloc and parsed_href.netloc != initial_domain:
                                    best_href = href
                                    break
                except Exception:
                    continue
            if best_href:
                break
                
        if best_href:
            print(f"   🔗 [External Portal] Found external apply URL: {best_href}")
            await page.goto(best_href, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(3000)
            await self._handle_cloudflare(page)
            return True
            
        # 3. If no direct link with external href was found, try clicking the apply buttons/links to see if it redirects or opens modal
        # We look for a button or link with apply text
        for text_pat in texts_to_check:
            selectors = [
                f'a:has-text("{text_pat}")',
                f'button:has-text("{text_pat}")',
                f'a:has-text("{text_pat.capitalize()}")',
                f'button:has-text("{text_pat.capitalize()}")',
                f'a:has-text("{text_pat.title()}")',
                f'button:has-text("{text_pat.title()}")',
            ]
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    count = await loc.count()
                    if count > 0:
                        el = loc.first
                        if await el.is_visible() and await el.is_enabled():
                            # Try clicking and wait for navigation or new page/popup
                            print(f"   🖱️ [External Portal] Clicking element '{text_pat}' using selector '{sel}'")
                            
                            # Set up popup listener just in case it opens a new tab
                            popup_promise = page.context.wait_for_event("page", timeout=5000)
                            
                            # Click the button
                            await el.click()
                            
                            try:
                                # Wait for new page (tab) if opened
                                new_page = await popup_promise
                                await new_page.wait_for_load_state("domcontentloaded")
                                print(f"   🆕 [External Portal] New tab opened: {new_page.url}")
                                target_url = new_page.url
                                await new_page.close()
                                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                                await page.wait_for_timeout(3000)
                                await self._handle_cloudflare(page)
                                return True
                            except Exception as popup_err:
                                # No new tab, check if page navigated or opened a modal
                                pass
                                
                            # Wait to see if the URL changed
                            await page.wait_for_timeout(2000)
                            await self._handle_cloudflare(page)
                            if urllib.parse.urlparse(page.url).netloc != initial_domain:
                                print(f"   🚀 [External Portal] Navigated to: {page.url}")
                                return True
                                
                            # Check if a modal or new link became visible (like on Remotive)
                            # We re-query <a> tags
                            new_links = await page.query_selector_all('a')
                            for nl in new_links:
                                try:
                                    if not await nl.is_visible():
                                        continue
                                    n_text = (await nl.inner_text()).lower().strip()
                                    if any(tp in n_text for tp in texts_to_check):
                                        n_href = await nl.get_attribute("href")
                                        if n_href:
                                            n_href_lower = n_href.lower().strip()
                                            if n_href_lower.startswith("http") or n_href_lower.startswith("//"):
                                                parsed_nhref = urllib.parse.urlparse(n_href)
                                                if parsed_nhref.netloc and parsed_nhref.netloc != initial_domain:
                                                    print(f"   🔗 [External Portal] Found external apply URL in modal/change: {n_href}")
                                                    await page.goto(n_href, wait_until="domcontentloaded", timeout=60000)
                                                    await page.wait_for_timeout(3000)
                                                    await self._handle_cloudflare(page)
                                                    return True
                                except Exception as link_err:
                                    continue
                except Exception as sel_err:
                    print(f"   ⚠️ [resolve_redirects] Error checking selector '{sel}': {sel_err}")
                    continue
                    
        return False

    async def apply(self, page, job_url: str, resume_pdf_path: str) -> str:
        # Resolve potential aggregator redirects first
        await self.resolve_redirects(page)

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
