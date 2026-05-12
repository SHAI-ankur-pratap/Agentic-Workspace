"""
Debug script — runs ONE LinkedIn job application with full screenshots.
Run from terminal: python debug_apply.py
Screenshots saved to debug_screenshots/
"""
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

SCREENSHOTS = Path("debug_screenshots")
SCREENSHOTS.mkdir(exist_ok=True)

EMAIL = os.getenv("LINKEDIN_EMAIL")
PASSWORD = os.getenv("LINKEDIN_PASSWORD")
SESSION_FILE = "linkedin_session.json"

async def snap(page, name):
    path = str(SCREENSHOTS / f"{name}.png")
    await page.screenshot(path=path, full_page=False)
    print(f"  📸 Screenshot: {path}")

async def main():
    async with async_playwright() as p:
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        browser = await p.chromium.launch(
            headless=False,
            executable_path=chrome_path if os.path.exists(chrome_path) else None,
            args=["--no-first-run", "--no-default-browser-check"],
        )

        # --- LOGIN ---
        if os.path.exists(SESSION_FILE):
            print(f"🔓 Loading saved session...")
            context = await browser.new_context(storage_state=SESSION_FILE)
        else:
            context = await browser.new_context()

        page = await context.new_page()

        # Check if logged in
        print("🔍 Checking login status...")
        await page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await snap(page, "01_initial_page")

        if "feed" not in page.url:
            print(f"⚠️ Not logged in (at {page.url}). Logging in...")
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await snap(page, "02_login_page")

            # Find and fill login fields
            for _ in range(15):
                await page.wait_for_timeout(1000)
                username_field = await page.query_selector("input#username, input[name='session_key']")
                if username_field:
                    break
            else:
                print("❌ Login form not found!")
                await snap(page, "02_login_failed")
                await browser.close()
                return

            await username_field.fill(EMAIL)
            pw = await page.query_selector("input#password, input[type='password']")
            await pw.fill(PASSWORD)
            await page.click("button[type='submit']")
            print("⏳ Waiting 90 seconds for 2FA approval on your phone...")
            await page.wait_for_timeout(90000)
            await snap(page, "03_after_2fa")

            if "feed" not in page.url:
                print(f"❌ Login failed. Page: {page.url}")
                await browser.close()
                return

            await context.storage_state(path=SESSION_FILE)
            print("✅ Logged in and session saved.")
        else:
            print("✅ Already logged in.")

        # --- FIND JOBS ---
        print("\n🔍 Searching for QA Lead jobs (Easy Apply)...")
        search_url = "https://www.linkedin.com/jobs/search/?keywords=QA%20Lead&f_AL=true&sortBy=DD"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await snap(page, "04_job_search")

        # Count job links
        count = await page.evaluate("document.querySelectorAll('a[href*=\"/jobs/view/\"]').length")
        print(f"  Found {count} job links with a[href*='/jobs/view/']")

        jobs = await page.evaluate("""() => {
            const seen = new Set();
            return Array.from(document.querySelectorAll('a[href*="/jobs/view/"]'))
                .map(a => ({title: (a.textContent || '').trim(), href: a.href.split('?')[0]}))
                .filter(j => {
                    if (j.title.length < 3 || seen.has(j.href)) return false;
                    seen.add(j.href);
                    return true;
                }).slice(0, 5);
        }""")

        if not jobs:
            print("❌ No jobs found! Check screenshot 04_job_search.png")
            await browser.close()
            return

        print(f"  First 5 jobs:")
        for j in jobs:
            print(f"    • {j['title'][:50]} → {j['href'][:60]}")

        # --- OPEN FIRST JOB ---
        first_job = jobs[0]
        print(f"\n📄 Opening: {first_job['title'][:60]}")
        print(f"   URL: {first_job['href']}")

        job_page = await context.new_page()
        await job_page.goto(first_job['href'], wait_until="domcontentloaded", timeout=30000)
        # Wait for any apply button (catches it before React re-hydrates)
        APPLY_BTN = ('button:has-text("Easy Apply"), button.apply-button, '
                     'button.jobs-apply-button, button:has-text("Apply"), '
                     "button:has-text(\"I'm interested\")")
        try:
            await job_page.wait_for_selector(APPLY_BTN, timeout=8000)
            print("  ✅ Apply button appeared!")
        except Exception:
            print("  ⚠️ No apply button appeared within 8s")
        await snap(job_page, "05_job_detail")

        # --- CHECK JD ---
        for sel in [".show-more-less-html__markup", ".description__text", ".jobs-description-content__text"]:
            el = await job_page.query_selector(sel)
            if el:
                text = await el.inner_text()
                if text and len(text) > 50:
                    print(f"  ✅ JD found via '{sel}': {text[:100]}...")
                    break
        else:
            print("  ⚠️ JD not found with any selector")

        # --- CHECK COMPANY ---
        for sel in [".topcard__org-name-link", ".jobs-unified-top-card__company-name",
                    ".job-details-jobs-unified-top-card__company-name a"]:
            el = await job_page.query_selector(sel)
            if el:
                company = (await el.inner_text()).strip()
                if company:
                    print(f"  ✅ Company: '{company}' via '{sel}'")
                    break
        else:
            print("  ⚠️ Company not found")

        # --- FIND APPLY BUTTON ---
        print("\n🔍 Scanning for Apply button...")
        all_buttons = await job_page.evaluate("""() =>
            Array.from(document.querySelectorAll('button'))
                .filter(b => {
                    const r = b.getBoundingClientRect();
                    return r.width > 0 && b.textContent.trim().length > 0 && b.textContent.trim().length < 30;
                })
                .map(b => ({text: b.textContent.trim(), cls: b.className.slice(0, 80)}))
        """)
        print(f"  All visible buttons on job page:")
        for btn in all_buttons:
            print(f"    [{btn['text']}] cls={btn['cls'][:60]}")

        apply_selectors = [
            'button:has-text("Easy Apply")',
            'button.jobs-apply-button',
            'button.apply-button',
            'button[data-tracking-control-name*="apply"]',
            'button[data-control-name="jobdetails_topcard_inapply"]',
            'button:has-text("Apply")',
        ]
        apply_btn_sel = None
        for sel in apply_selectors:
            try:
                el = await job_page.query_selector(sel)
                if el:
                    has_size = await job_page.evaluate(
                        f"() => {{ const el = document.querySelector({repr(sel)}); return el ? el.getBoundingClientRect().width > 0 : false; }}"
                    )
                    if has_size:
                        text = await el.inner_text()
                        print(f"\n  ✅ Apply button found: '{sel}' → text='{text.strip()}'")
                        apply_btn_sel = sel
                        break
            except Exception as e:
                print(f"  ⚠️ Selector '{sel}' error: {e}")
        else:
            if not apply_btn_sel:
                print("\n  ❌ NO APPLY BUTTON FOUND! Check screenshot 05_job_detail.png")
                await job_page.close()
                await browser.close()
                return

        await snap(job_page, "06_before_click_apply")

        # --- CLICK APPLY ---
        print(f"\n🖱️ Clicking Apply button ({apply_btn_sel})...")
        try:
            async with context.expect_page(timeout=5000) as new_page_info:
                btn = job_page.locator(apply_btn_sel).first
                await btn.click(force=True)
            ext_page = await new_page_info.value
            await ext_page.wait_for_load_state("domcontentloaded", timeout=15000)
            await snap(ext_page, "07_external_portal")
            print(f"  🔗 Opened EXTERNAL portal: {ext_page.url}")
            print("  → External portal handling would take over here.")
            await ext_page.close()
        except Exception:
            # No new tab — check for modal on same page
            await job_page.wait_for_timeout(3000)
            await snap(job_page, "07_after_click_apply")

            # Check for modal
            modal = await job_page.query_selector('[data-test-modal], [role="dialog"], .jobs-easy-apply-modal, .artdeco-modal')
            if modal:
                print("  ✅ Easy Apply MODAL opened!")
                await snap(job_page, "08_easy_apply_modal")

                # Check modal contents
                modal_html = await modal.inner_html()
                print(f"  Modal content preview: {modal_html[:200]}")

                # Find buttons in modal
                modal_buttons = await job_page.evaluate("""() =>
                    Array.from(document.querySelectorAll('[role="dialog"] button, [data-test-modal] button, .artdeco-modal button'))
                        .filter(b => b.getBoundingClientRect().width > 0)
                        .map(b => b.textContent.trim())
                        .filter(t => t.length > 0)
                """)
                print(f"  Buttons in modal: {modal_buttons}")
            else:
                print(f"  ⚠️ No modal found. Current URL: {job_page.url}")
                # Check if URL changed
                if "linkedin.com" not in job_page.url:
                    print(f"  → Redirected to: {job_page.url}")
                else:
                    print("  ❌ CLICK DID NOTHING — button may require login or have anti-bot")

        print("\n✅ Debug complete. Check debug_screenshots/ for all screenshots.")
        print("Press Ctrl+C or close Chrome to exit.")
        await asyncio.sleep(30)  # Keep browser open for inspection
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
