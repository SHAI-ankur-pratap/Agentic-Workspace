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

LINKEDIN_FEED_INDICATOR = ".global-nav__me-photo"


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
            el = await page.query_selector(LINKEDIN_FEED_INDICATOR)
            return el is not None
        except Exception:
            return False

    async def auto_login(self, page) -> bool:
        if os.path.exists(self.state_file):
            if await self._is_logged_in(page):
                print("✅ LinkedIn session valid.")
                return True
            print("⚠️ LinkedIn session expired. Re-logging in...")
            os.remove(self.state_file)

        print(f"🤖 Logging into LinkedIn as {self.email}...")
        try:
            await page.goto(self.login_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠️ Login page load warning: {e} — continuing anyway")

        # Wait for login form or already-logged-in feed
        for _ in range(15):
            await page.wait_for_timeout(1000)
            current_url = page.url
            if "feed" in current_url or "mynetwork" in current_url:
                await page.context.storage_state(path=self.state_file)
                print("✅ Already logged in!")
                return True
            username_field = await page.query_selector("input#username, input[name='session_key'], input[autocomplete='username']")
            if username_field:
                break
        else:
            print("⚠️ Login form not found after 15s. Taking screenshot.")
            await page.screenshot(path="linkedin_login_error.png")
            return False

        try:
            await username_field.fill(self.email)
            pw_field = await page.query_selector("input#password, input[name='session_password'], input[type='password']")
            if pw_field:
                await pw_field.fill(self.password)
            await page.click("button[type='submit'], button[data-litms-control-urn='login-submit']")
        except Exception as e:
            print(f"⚠️ Login form fill error: {e}")
            await page.screenshot(path="linkedin_login_error.png")
            return False

        print("⏳ Waiting 90s for 2FA approval on your phone...")
        await page.wait_for_timeout(90000)

        if "feed" in page.url or ("linkedin.com" in page.url and "login" not in page.url and "checkpoint" not in page.url):
            await page.context.storage_state(path=self.state_file)
            print("✅ Login successful. Session saved.")
            return True

        print("⚠️ Login failed (CAPTCHA/OTP/timeout).")
        await page.screenshot(path="linkedin_login_error.png")
        return False

    async def login_and_save_state(self, url):
        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()
            await self.auto_login(page)
            await browser.close()

    async def _extract_jd(self, page) -> str:
        for sel in [
            ".jobs-description-content__text",
            ".jobs-box__html-content",
            ".job-view-layout",
            "#job-details",
        ]:
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
        for sel in [
            ".jobs-unified-top-card__company-name",
            ".topcard__org-name-link",
            ".jobs-details-top-card__company-url",
        ]:
            try:
                el = await page.query_selector(sel)
                if el:
                    return (await el.inner_text()).strip()
            except Exception:
                continue
        return "UnknownCompany"

    async def _click_easy_apply(self, page, context) -> tuple:
        """Click the Easy Apply button. Returns (success, external_page).
        external_page is None for Easy Apply modal, or a Page object for external redirects."""
        selectors = [
            'button.jobs-apply-button',
            'button[data-control-name="jobdetails_topcard_inapply"]',
            '.jobs-s-apply button',
            'button:has-text("Easy Apply")',
            'button:has-text("Apply")',
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() == 0 or not await btn.is_visible():
                    continue
                print(f"   🖱️ Clicking Apply button...")

                # Try to catch a new tab opening (external company site)
                try:
                    async with context.expect_page(timeout=4000) as new_page_info:
                        await btn.click()
                    ext_page = await new_page_info.value
                    await ext_page.wait_for_load_state("domcontentloaded", timeout=15000)
                    print(f"   🔗 Opened external site in new tab: {ext_page.url}")
                    return True, ext_page
                except Exception:
                    pass  # No new tab — fall through to modal/same-page check

                # Check for Easy Apply modal on current page
                try:
                    await page.wait_for_selector(
                        '[data-test-modal], [role="dialog"], .jobs-easy-apply-modal',
                        timeout=5000,
                    )
                    print("   ✅ Easy Apply modal opened!")
                    return True, None
                except Exception:
                    pass

                # Same-page URL redirect (rare on LinkedIn)
                await page.wait_for_timeout(2000)
                if "linkedin.com" not in page.url:
                    print(f"   🔗 Redirected on same page: {page.url}")
                    return True, page

                print(f"  ⚠️ Button clicked but nothing opened for selector: {sel}")
                return False, None

            except Exception:
                continue

        print("  ⚠️ Easy Apply button not found on this job.")
        return False, None

    async def _handle_easy_apply_modal(self, page, profile, resume_pdf_path, filler) -> str:
        """Step through the Easy Apply modal, filling each screen. Returns outcome string."""
        resume_uploaded = False

        for step in range(10):
            await page.wait_for_timeout(2000)
            print(f"   📋 Modal step {step + 1}...")

            # Verify modal is still open
            modal = await page.query_selector(
                '[data-test-modal], [role="dialog"], .jobs-easy-apply-modal'
            )
            if not modal:
                # Modal closed — check for success confirmation
                try:
                    page_text = await page.evaluate("() => document.body.innerText.toLowerCase()")
                    if any(kw in page_text for kw in [
                        "application submitted", "applied successfully", "your application was sent",
                        "done", "application sent"
                    ]):
                        print("   ✅ Application confirmed submitted!")
                        return "applied"
                except Exception:
                    pass
                print("  ⚠️ Modal closed without confirmation.")
                return "failed"

            # Upload resume (only once, on the step that has a file input)
            if not resume_uploaded:
                try:
                    file_input = await page.query_selector('input[type="file"]')
                    if file_input and os.path.exists(resume_pdf_path):
                        await file_input.set_input_files(resume_pdf_path)
                        resume_uploaded = True
                        print(f"   📎 Resume uploaded at step {step + 1}")
                        await page.wait_for_timeout(1500)
                except Exception as e:
                    print(f"   ⚠️ Resume upload error: {e}")

            # Fill any visible form fields
            await filler.parse_and_fill(page, page.url)
            await page.wait_for_timeout(500)

            # Check for Submit button first
            submit_btn = page.locator(
                'button:has-text("Submit application"), '
                'button:has-text("Submit Application"), '
                'button:has-text("Submit")'
            )
            if await submit_btn.count() > 0:
                try:
                    if await submit_btn.first.is_visible():
                        print("   🚀 Clicking Submit application...")
                        await submit_btn.first.click()
                        await page.wait_for_timeout(3000)
                        # Check for confirmation
                        try:
                            page_text = await page.evaluate(
                                "() => document.body.innerText.toLowerCase()"
                            )
                            if any(kw in page_text for kw in [
                                "application submitted", "applied successfully",
                                "your application was sent", "done", "application sent"
                            ]):
                                print("   ✅ Confirmed: Application submitted!")
                                return "applied"
                        except Exception:
                            pass
                        print("   ✅ Submit clicked (no confirmation text found, marking applied).")
                        return "applied"
                except Exception as e:
                    print(f"   ⚠️ Submit click error: {e}")

            # Try Next / Review / Continue
            next_selectors = [
                'button:has-text("Next")',
                'button:has-text("Review your application")',
                'button:has-text("Review")',
                'button:has-text("Continue to next step")',
                'button:has-text("Continue")',
            ]
            clicked_next = False
            for nsel in next_selectors:
                try:
                    nbtn = page.locator(nsel).first
                    if await nbtn.count() > 0 and await nbtn.is_visible():
                        print(f"   ➡️ Clicking '{nsel}'...")
                        await nbtn.click()
                        clicked_next = True
                        break
                except Exception:
                    continue

            if not clicked_next:
                print("  ⚠️ No Next/Submit button found in modal.")
                return "failed"

        print("  ⚠️ Reached max steps without submitting.")
        return "failed"

    async def apply_to_job(self, job_url: str, profile: dict, generator=None):
        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            jd = await self._extract_jd(page)
            company = await self._extract_company(page)
            tailor = CVTailor()
            tailored_md = tailor.rewrite_cv(jd or job_url)
            cv_path = "tailored_cv_single.pdf"
            await tailor.generate_pdf(tailored_md, cv_path)
            filler = UniversalFormFiller(profile)

            ext_page = None
            try:
                modal_opened, ext_page = await self._click_easy_apply(page, context)
                if not modal_opened:
                    print("⚠️ Easy Apply button not found or modal did not open.")
                    outcome = "failed"
                elif ext_page is not None:
                    portal = ExternalPortalAgent(profile, filler)
                    outcome = await portal.apply(ext_page, ext_page.url, cv_path)
                else:
                    outcome = await self._handle_easy_apply_modal(page, profile, cv_path, filler)
            except Exception as e:
                print(f"⚠️ Apply error: {e}")
                outcome = "failed"
            finally:
                if ext_page is not None and ext_page != page:
                    try:
                        await ext_page.close()
                    except Exception:
                        pass
                if os.path.exists(cv_path):
                    os.remove(cv_path)

            await browser.close()
            print(f"Outcome: {outcome}")

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
                print(f"\n🔍 LinkedIn: searching '{role}' (Easy Apply only)...")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    print(f"⚠️ Navigation: {e}")
                await page.wait_for_timeout(4000)

                for page_num in range(1, 4):
                    print(f"\n📄 Page {page_num}...")
                    await page.evaluate(
                        "document.querySelector('.jobs-search-results-list')?.scrollTo(0, 9999)"
                    )
                    await page.wait_for_timeout(3000)

                    job_cards = await page.evaluate("""() => {
                        const anchors = Array.from(document.querySelectorAll(
                            'a.job-card-list__title--link, a[class*="job-card-list__title"], a[class*="base-search-card__title"]'
                        ));
                        return anchors.map((a, idx) => ({
                            index: idx,
                            title: a.textContent.trim(),
                            href: a.href || ''
                        })).filter(j => j.title.length > 3);
                    }""")

                    if not job_cards:
                        print("No cards found, stopping pagination.")
                        break

                    print(f"✅ {len(job_cards)} cards found")

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
                        ext_page = None
                        try:
                            modal_opened, ext_page = await self._click_easy_apply(page, context)

                            if not modal_opened:
                                print(f"  ⚠️ Could not open Apply for: {title[:40]}")
                                outcome = "failed"
                            elif ext_page is not None:
                                # External company portal opened (new tab or redirect)
                                filler = UniversalFormFiller(profile)
                                portal = ExternalPortalAgent(profile, filler)
                                outcome = await portal.apply(ext_page, ext_page.url, cv_path)
                            else:
                                # Easy Apply modal is open on LinkedIn
                                filler = UniversalFormFiller(profile)
                                outcome = await self._handle_easy_apply_modal(
                                    page, profile, cv_path, filler
                                )

                        except Exception as e:
                            print(f"  ⚠️ Apply error: {e}")
                            outcome = "failed"
                        finally:
                            if ext_page is not None and ext_page != page:
                                try:
                                    await ext_page.close()
                                except Exception:
                                    pass
                            if os.path.exists(cv_path):
                                os.remove(cv_path)

                        db.mark_processed(job_id, "linkedin", outcome,
                                          title=title, company=company,
                                          url=job_url, score=job_score)
                        stats[outcome if outcome in stats else "failed"] += 1
                        print(f"  → Outcome: {outcome}")

                        await page.wait_for_timeout(random.randint(8, 20) * 1000)

                    try:
                        has_next = await page.evaluate("""() => {
                            const btn = Array.from(document.querySelectorAll('button')).find(
                                b => (b.getAttribute('aria-label') || '').toLowerCase().includes('next')
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

        print(
            f"\n📊 LinkedIn → ✅ Applied:{stats['applied']} ⏭ Skipped:{stats['skipped']} "
            f"❌ Failed:{stats['failed']} 📋 Manual:{stats['manual']}"
        )
        return stats
