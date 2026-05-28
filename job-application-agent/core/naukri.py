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

    async def auto_login(self, page) -> bool:
        if os.path.exists(self.state_file):
            print("🔓 Loading Naukri session...")
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
                const u = document.querySelector('input[placeholder*="mail"], input[placeholder*="Mobile"]');
                const pw = document.querySelector('input[type="password"]');
                if (u) u.value = '{self.email}';
                if (pw) pw.value = '{self.password}';
            }}""")
        await page.wait_for_timeout(4000)
        await page.context.storage_state(path=self.state_file)
        print("✅ Naukri session saved.")
        return True

    async def login_and_save_state(self, url):
        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()
            await self.auto_login(page)
            await browser.close()

    async def _extract_jd(self, page) -> str:
        for sel in [
            ".styles_job-desc-container__txpYf",
            ".job-desc",
            "[class*='description']",
            ".JDC",
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
            ".styles_jd-header-comp-name__MvqAI",
            ".comp-name",
            "[class*='company-name']",
        ]:
            try:
                el = await page.query_selector(sel)
                if el:
                    return (await el.inner_text()).strip()
            except Exception:
                continue
        return "UnknownCompany"

    async def apply_to_job(self, job_url: str, profile: dict, generator=None):
        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()
            await self.auto_login(page)
            await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            jd = await self._extract_jd(page)
            tailor = CVTailor()
            with open(tailor.base_cv_path, "r") as _f:
                tailored_md = _f.read()
            cv_path = "tailored_cv_single_naukri.pdf"
            await tailor.generate_pdf(tailored_md, cv_path)
            filler = UniversalFormFiller(profile)
            filled = await filler.parse_and_fill(page, job_url)
            print(f"Apply form filled: {filled}")
            if os.path.exists(cv_path):
                os.remove(cv_path)
            await browser.close()
            return "applied" if filled else "failed"

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
                print(f"\n🔍 Naukri: searching '{role}'...")
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                except Exception as e:
                    print(f"⚠️ Navigation: {e}")
                await page.wait_for_timeout(4000)

                for page_num in range(1, 4):
                    print(f"\n📄 Page {page_num}...")
                    await page.wait_for_timeout(3000)

                    job_cards = await page.evaluate("""() => {
                        const titleLinks = Array.from(document.querySelectorAll(
                            'a.title, a[class*="title"], .jobTuple a, article a[href*="job-listings"]'
                        ));
                        const seen = new Set();
                        return titleLinks
                            .map((a, idx) => ({
                                index: idx,
                                title: a.textContent.trim(),
                                href: a.href || ''
                            }))
                            .filter(j => {
                                if (!j.title || j.title.length < 3 || seen.has(j.href)) return false;
                                seen.add(j.href);
                                return true;
                            });
                    }""")

                    if not job_cards:
                        print("No cards found, stopping pagination.")
                        break

                    print(f"✅ {len(job_cards)} cards found")

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
                        with open(tailor.base_cv_path, "r") as _f:
                            tailored_md = _f.read()
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

        print(
            f"\n📊 Naukri → ✅ Applied:{stats['applied']} ⏭ Skipped:{stats['skipped']} "
            f"❌ Failed:{stats['failed']} 📋 Manual:{stats['manual']}"
        )
        return stats
