import asyncio
import os
from playwright.async_api import async_playwright

class JobBrowserAgent:
    def __init__(self, headless=False, state_file="session_state.json"):
        self.headless = headless
        self.state_file = state_file

    async def get_browser(self, p):
        # Use args to bypass any profile selection or first-run dialogues
        args = [
            "--no-default-browser-check",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-fre",
            "--disable-sync"
        ]
        
        # Use the real Google Chrome binary to bypass Akamai/Cloudflare bot protection
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(chrome_path):
            return await p.chromium.launch(headless=self.headless, executable_path=chrome_path, args=args)
        
        return await p.chromium.launch(headless=self.headless, args=args)

    async def get_context(self, browser):
        if os.path.exists(self.state_file):
            print(f"🔓 Loading saved session from {self.state_file}")
            return await browser.new_context(storage_state=self.state_file)
        return await browser.new_context()

    async def navigate_to_job(self, url: str):
        try:
            async with async_playwright() as p:
                browser = await self.get_browser(p)
                context = await self.get_context(browser)
                page = await context.new_page()
                print(f"🔗 Navigating to {url}...")
                await page.goto(url)
                title = await page.title()
                print(f"✅ Reached page: {title}")
                await page.wait_for_timeout(2000)
                await page.screenshot(path="job_snapshot.png")
                await browser.close()
        except Exception as e:
            print(f"❌ Browser error: {e}")
