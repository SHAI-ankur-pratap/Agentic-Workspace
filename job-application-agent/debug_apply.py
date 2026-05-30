"""
Debug script — traces ONE LinkedIn job application end-to-end with screenshots.
Run: python debug_apply.py
Screenshots saved to debug_screenshots/
"""
import asyncio, os, sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

SCREENSHOTS = Path("debug_screenshots")
SCREENSHOTS.mkdir(exist_ok=True)

EMAIL    = os.getenv("LINKEDIN_EMAIL")
PASSWORD = os.getenv("LINKEDIN_PASSWORD")
SESSION  = "linkedin_session.json"

JS_FIND_APPLY = """() => {
    const keywords = ['easy apply', 'apply', 'interested'];
    const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const t = b.textContent.trim().toLowerCase();
        const r = b.getBoundingClientRect();
        return r.width > 0 && keywords.some(k => t.includes(k));
    });
    if (!btn) return null;
    return {
        text: btn.textContent.trim(),
        charCodes: Array.from(btn.textContent.trim()).map(c => c.charCodeAt(0)).join(',')
    };
}"""

JS_CLICK_APPLY = """() => {
    const keywords = ['easy apply', 'apply', 'interested'];
    const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const t = b.textContent.trim().toLowerCase();
        const r = b.getBoundingClientRect();
        return r.width > 0 && keywords.some(k => t.includes(k));
    });
    if (btn) { btn.click(); return btn.textContent.trim(); }
    return null;
}"""

async def snap(page, name):
    path = str(SCREENSHOTS / f"{name}.png")
    await page.screenshot(path=path, full_page=False)
    print(f"  📸 {path}")

async def main():
    async with async_playwright() as p:
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        browser = await p.chromium.launch(
            headless=False,
            executable_path=chrome if os.path.exists(chrome) else None,
            args=["--no-first-run", "--no-default-browser-check"],
        )

        # Load session or login
        ctx = await browser.new_context(
            storage_state=SESSION if os.path.exists(SESSION) else None
        )
        page = await ctx.new_page()
        print("🔍 Checking login...")
        await page.goto("https://www.linkedin.com/feed", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await snap(page, "01_feed")

        if "feed" not in page.url and "mynetwork" not in page.url:
            print(f"⚠️ Not logged in ({page.url}). Logging in...")
            await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            for _ in range(15):
                await page.wait_for_timeout(1000)
                f = await page.query_selector("input#username, input[name='session_key']")
                if f: break
            else:
                print("❌ Login form not found"); await browser.close(); return
            await f.fill(EMAIL)
            pw = await page.query_selector("input#password, input[type='password']")
            await pw.fill(PASSWORD)
            await page.click("button[type='submit']")
            print("⏳ 90s for 2FA approval...")
            await page.wait_for_timeout(90000)
            if "feed" not in page.url:
                print(f"❌ Login failed: {page.url}"); await browser.close(); return
            await ctx.storage_state(path=SESSION)
            print("✅ Logged in.")
        else:
            print("✅ Already logged in.")

        # Search
        print("\n🔍 Searching for QA Lead jobs...")
        search = "https://www.linkedin.com/jobs/search/?keywords=QA%20Lead&f_AL=true&sortBy=DD"
        await page.goto(search, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await snap(page, "04_search")

        count = await page.evaluate("document.querySelectorAll('a[href*=\"/jobs/view/\"]').length")
        print(f"  Job links found: {count}")

        jobs = await page.evaluate("""() => {
            const seen = new Set();
            return Array.from(document.querySelectorAll('a[href*="/jobs/view/"]'))
                .map(a => ({title: (a.textContent || '').trim(), href: a.href.split('?')[0]}))
                .filter(j => { if (j.title.length < 3 || seen.has(j.href)) return false; seen.add(j.href); return true; })
                .slice(0, 5);
        }""")
        if not jobs:
            print("❌ No jobs found!"); await browser.close(); return
        print("  First jobs:")
        for j in jobs:
            print(f"    • {j['title'][:50]} → {j['href']}")

        # Open first job
        job = jobs[0]
        print(f"\n📄 {job['title'][:60]}\n   {job['href']}")
        job_page = await ctx.new_page()

        # Navigate and IMMEDIATELY try JS burst clicks before React hydrates
        print("\n⚡ Navigating and burst-clicking Apply before React hydrates...")
        await job_page.goto(job['href'], wait_until="domcontentloaded", timeout=30000)

        clicked_text = None
        for burst in range(10):
            info = await job_page.evaluate(JS_FIND_APPLY)
            if info:
                print(f"  Burst {burst+1}: found '{info['text']}' codes=[{info['charCodes'][:40]}]")
                clicked_text = await job_page.evaluate(JS_CLICK_APPLY)
                if clicked_text:
                    print(f"  ✅ JS clicked: '{clicked_text}'")
                    break
            else:
                print(f"  Burst {burst+1}: no button yet...")
            await asyncio.sleep(0.2)

        await snap(job_page, "05_job_after_bursts")

        if not clicked_text:
            print("\n❌ Could not click any apply button in burst window.")
            # Show all buttons for diagnosis
            btns = await job_page.evaluate("""() =>
                Array.from(document.querySelectorAll('button'))
                    .filter(b => b.getBoundingClientRect().width > 0 && b.textContent.trim().length > 0)
                    .map(b => b.textContent.trim())
            """)
            print(f"  All visible buttons: {btns}")
        else:
            # Wait for modal or external page
            await asyncio.sleep(3)
            await snap(job_page, "06_after_click")

            modal = await job_page.query_selector('[data-test-modal], [role="dialog"], .artdeco-modal')
            if modal:
                modal_btns = await job_page.evaluate("""() =>
                    Array.from(document.querySelectorAll('[role="dialog"] button, .artdeco-modal button'))
                        .filter(b => b.getBoundingClientRect().width > 0)
                        .map(b => b.textContent.trim())
                """)
                print(f"  ✅ MODAL opened! Buttons: {modal_btns}")
                await snap(job_page, "07_modal")
            else:
                print(f"  ⚠️ No modal. URL: {job_page.url}")
                # Check if it silently applied (I'm interested confirmation)
                text = await job_page.evaluate("() => document.body.innerText.slice(0, 300)")
                print(f"  Page text: {text[:200]}")

        # JD extraction
        print("\n📝 JD extraction:")
        jd = await job_page.evaluate("""() => {
            const sels = ['.show-more-less-html__markup', '.description__text', '.jobs-description-content__text'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.textContent.trim().length > 100) return {sel: s, text: el.innerText.slice(0, 200)};
            }
            // About the job section
            const h = Array.from(document.querySelectorAll('h2, h3')).find(e => e.textContent.trim() === 'About the job');
            if (h) {
                const sec = h.closest('section') || h.parentElement;
                if (sec) return {sel: 'About the job section', text: sec.innerText.slice(0, 200)};
            }
            // Grab p/li blocks
            const blocks = Array.from(document.querySelectorAll('p, li')).filter(e => e.textContent.trim().length > 40);
            if (blocks.length) return {sel: 'p/li blocks', text: blocks.slice(0, 5).map(e => e.textContent.trim()).join(' ').slice(0, 200)};
            return null;
        }""")
        if jd:
            print(f"  ✅ Found via '{jd['sel']}': {jd['text'][:120]}...")
        else:
            print("  ❌ JD not found")

        print("\n✅ Debug done. Browser stays open 30s for inspection.")
        await asyncio.sleep(30)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
