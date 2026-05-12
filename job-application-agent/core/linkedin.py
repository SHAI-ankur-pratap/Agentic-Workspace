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

    async def _collect_job_urls(self, page, role: str) -> list:
        """Scrape ALL job URLs for a role across pages before touching any. Returns [(url, title)]."""
        search_query = "%20".join(role.split())
        search_url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}&f_AL=true&sortBy=DD"
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠️ Search navigation: {e}")
        await page.wait_for_timeout(4000)

        seen_urls = set()
        collected = []

        for page_num in range(1, 5):
            print(f"  Collecting page {page_num}...")
            try:
                await page.evaluate(
                    "document.querySelector('.jobs-search-results-list')?.scrollTo(0, 9999)"
                )
            except Exception:
                pass
            await page.wait_for_timeout(3000)

            cards = await page.evaluate("""() => {
                const anchors = Array.from(document.querySelectorAll(
                    'a.job-card-list__title--link, a[class*="job-card-list__title"], a[class*="base-search-card__title"]'
                ));
                return anchors.map(a => ({
                    title: a.textContent.trim(),
                    href: (a.href || '').split('?')[0]
                })).filter(j => j.title.length > 3 && j.href.includes('/jobs/view/'));
            }""")

            new_cards = 0
            for c in cards:
                if c["href"] and c["href"] not in seen_urls:
                    seen_urls.add(c["href"])
                    collected.append((c["href"], c["title"]))
                    new_cards += 1

            print(f"  +{new_cards} new jobs (total: {len(collected)})")
            if not cards or new_cards == 0:
                break

            # Go to next page
            try:
                went_next = await page.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('button')).find(
                        b => (b.getAttribute('aria-label') || '').toLowerCase().includes('next')
                    );
                    if (btn && !btn.disabled) { btn.click(); return true; }
                    return false;
                }""")
                if not went_next:
                    break
                await page.wait_for_timeout(4000)
            except Exception:
                break

        return collected

    async def _process_single_job(self, context, job_url: str, job_title: str,
                                   role: str, profile: dict, db, stats: dict) -> str:
        """Open a job page directly, score, tailor CV, apply. Returns outcome string."""
        # Open job in a dedicated tab so the search page stays intact
        job_page = await context.new_page()
        try:
            await job_page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  ⚠️ Page load: {e}")
            await job_page.close()
            return "failed"

        await job_page.wait_for_timeout(2000)

        jd = await self._extract_jd(job_page)
        company = await self._extract_company(job_page)
        job_id = db.generate_job_id(company, job_title)

        if db.is_processed(job_id):
            await job_page.close()
            stats["skipped"] += 1
            return "skipped"

        # Score
        job_filter = JobFilter(profile)
        result = job_filter.score_job(job_title, jd or job_title)
        job_score = result.get("score", 0)
        if not result["passed"]:
            db.mark_processed(job_id, "linkedin", "skipped_low_score",
                              title=job_title, company=company,
                              url=job_url, score=job_score)
            stats["skipped"] += 1
            await job_page.close()
            return "skipped_low_score"

        # Tailor CV
        tailor = CVTailor()
        tailored_md = tailor.rewrite_cv(jd or job_title)
        cv_path = f"tailored_linkedin_cv_{job_id[:8]}.pdf"
        await tailor.generate_pdf(tailored_md, cv_path)

        outcome = "failed"
        ext_page = None
        try:
            modal_opened, ext_page = await self._click_easy_apply(job_page, context)

            if not modal_opened:
                print(f"  ⚠️ Apply button not found.")
                outcome = "failed"
            elif ext_page is not None:
                filler = UniversalFormFiller(profile)
                portal = ExternalPortalAgent(profile, filler)
                outcome = await portal.apply(ext_page, ext_page.url, cv_path)
            else:
                filler = UniversalFormFiller(profile)
                outcome = await self._handle_easy_apply_modal(
                    job_page, profile, cv_path, filler
                )
        except Exception as e:
            print(f"  ⚠️ Apply error: {e}")
            outcome = "failed"
        finally:
            if ext_page is not None and ext_page != job_page:
                try:
                    await ext_page.close()
                except Exception:
                    pass
            if os.path.exists(cv_path):
                os.remove(cv_path)
            try:
                await job_page.close()
            except Exception:
                pass

        db.mark_processed(job_id, "linkedin", outcome,
                          title=job_title, company=company,
                          url=job_url, score=job_score)
        stats[outcome if outcome in stats else "failed"] += 1
        return outcome

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
                # Collect all job URLs first, then navigate directly to each.
                # This avoids index-shifting when LinkedIn re-renders the list.
                job_urls = await self._collect_job_urls(page, role)
                print(f"\n✅ Collected {len(job_urls)} unique jobs for '{role}'")

                for job_url, job_title in job_urls:
                    job_id = db.generate_job_id("linkedin_" + role, job_title)
                    if db.is_processed(job_id):
                        stats["skipped"] += 1
                        continue

                    print(f"\n  → {job_title[:55]}")
                    print(f"     {job_url[:70]}")

                    try:
                        outcome = await asyncio.wait_for(
                            self._process_single_job(
                                context, job_url, job_title, role, profile, db, stats
                            ),
                            timeout=240,  # 4 min hard cap per job — never get stuck
                        )
                    except asyncio.TimeoutError:
                        print(f"  ⏱️ Job timed out after 4 min — moving on.")
                        db.mark_processed(job_id, "linkedin", "failed",
                                          title=job_title, url=job_url)
                        stats["failed"] += 1
                        outcome = "failed"
                    except Exception as e:
                        print(f"  ⚠️ Unexpected error: {e}")
                        db.mark_processed(job_id, "linkedin", "failed",
                                          title=job_title, url=job_url)
                        stats["failed"] += 1
                        outcome = "failed"

                    print(f"  → Outcome: {outcome}")
                    await asyncio.sleep(random.randint(5, 12))

            await browser.close()

        print(
            f"\n📊 LinkedIn → ✅ Applied:{stats['applied']} ⏭ Skipped:{stats['skipped']} "
            f"❌ Failed:{stats['failed']} 📋 Manual:{stats['manual']}"
        )
        return stats
