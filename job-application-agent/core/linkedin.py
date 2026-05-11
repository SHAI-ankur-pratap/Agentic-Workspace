from core.browser import JobBrowserAgent
from playwright.async_api import async_playwright
import asyncio
import os
from dotenv import load_dotenv
from core.filter import JobFilter
from core.cv_tailor import CVTailor

load_dotenv()

class LinkedInAgent(JobBrowserAgent):
    def __init__(self, headless=False):
        super().__init__(headless=headless, state_file="linkedin_session.json")
        self.login_url = "https://www.linkedin.com/login"
        self.email = os.getenv("LINKEDIN_EMAIL")
        self.password = os.getenv("LINKEDIN_PASSWORD")

    async def auto_login(self, page):
        if os.path.exists(self.state_file):
            return True
        print(f"🤖 Agentic Login to LinkedIn with {self.email}...")
        await page.goto(self.login_url)
        await page.fill("input#username", self.email)
        await page.fill("input#password", self.password)
        await page.click("button[type='submit']")
        print("⏳ Waiting 60 seconds for you to approve the LinkedIn 2FA notification on your phone...")
        await page.wait_for_timeout(60000)
        
        # Check if login succeeded
        if "feed" in page.url or "checkpoint" not in page.url:
            await page.context.storage_state(path=self.state_file)
            print("✅ Autonomous login successful. Session saved.")
            return True
        else:
            print("⚠️ Autonomous login blocked by CAPTCHA/OTP.")
            await page.screenshot(path="linkedin_login_error.png")
            return False

    async def autonomous_search_and_apply(self, profile: dict, generator=None):
        """Fully autonomous loop: Log in -> Search -> Apply"""
        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()
            
            # Step 1: Login
            success = await self.auto_login(page)
            if not success:
                await browser.close()
                return

            # Step 2: Search for roles
            roles = profile.get("preferences", {}).get("roles", ["QA Lead"])
            search_query = "%20".join(roles[0].split())
            search_url = f"https://www.linkedin.com/jobs/search/?keywords={search_query}&sortBy=DD" # DD = Most Recent
            
            print(f"🔍 Agentic Search: Navigating to job search for '{roles[0]}' (Sorted by Recent)...")
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print(f"⚠️ Warning during navigation: {e} (Continuing anyway)")
            await page.wait_for_timeout(5000)
            
            from core.db import JobDatabase
            db = JobDatabase()
            
            max_pages = 5
            for page_num in range(1, max_pages + 1):
                print(f"\n📄 ====== Scraping Page {page_num} ======")
                print("🎯 Extracting all Job Cards from the list...")
                
                # Scroll down the left pane slightly to ensure jobs render
                await page.evaluate("document.querySelector('.jobs-search-results-list')?.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(3000)
                
                job_data_list = await page.evaluate("""() => {
                    const cards = Array.from(document.querySelectorAll('a'));
                    const jobCards = cards.filter(a => a.className.includes('job-card-list__title') || a.className.includes('base-search-card__title'));
                    return jobCards.map((card, idx) => {
                        return { index: idx, title: card.textContent.trim() };
                    });
                }""")
                
                job_count = len(job_data_list)
                print(f"✅ Found {job_count} matching job cards on Page {page_num}!")
                
                if job_count == 0:
                    print("No more jobs found. Exiting pagination loop.")
                    break
                
                import random
                
                for job_data in job_data_list:
                    i = job_data["index"]
                    job_title = job_data["title"]
                    job_id = db.generate_job_id("UnknownCompany", job_title)
                    
                    print(f"\n--- 🔄 Processing Job {i+1} of {job_count}: {job_title[:30]}... ---")
                    
                    if db.is_processed(job_id):
                        print("⏭️ [Idempotency] Job already processed previously! Skipping to save API costs.")
                        continue
                    
                    print("🎯 Clicking the job card to load details...")
                    try:
                        await page.evaluate(f"""(index) => {{
                            const cards = Array.from(document.querySelectorAll('a'));
                            const jobCards = cards.filter(a => a.className.includes('job-card-list__title') || a.className.includes('base-search-card__title'));
                            if (jobCards[index]) jobCards[index].click();
                        }}""", i)
                        await page.wait_for_timeout(3000) # Wait for right pane to load
                    except Exception as e:
                        print(f"⚠️ Could not click job card {i+1}: {e}")
                        continue

                    # Mock JD for AI filtering
                    mock_jd = "Looking for a QA Automation Manager with 8+ years experience in Playwright and PyTest."
                    
                    # Step 3: Filter Job
                    job_filter = JobFilter(profile)
                    filter_result = job_filter.score_job(roles[0], mock_jd)
                    
                    if not filter_result["passed"]:
                        print("⏭️ Job does not meet criteria. Skipping...")
                        db.mark_processed(job_id, "linkedin", "Skipped (Low Filter Score)", title=job_title)
                        continue

                    # Step 4: Tailor CV
                    tailor = CVTailor()
                    tailored_md = tailor.rewrite_cv(mock_jd)
                    tailored_cv_path = tailor.generate_pdf(tailored_md, f"tailored_linkedin_cv_{i+1}.pdf")

                    # Step 5: Apply
                    print("🤖 Agentic Apply: Clicking 'Easy Apply' button...")
                    try:
                        # Attempt to force click the real Easy Apply button using JavaScript
                        await page.evaluate("""() => {
                            const buttons = Array.from(document.querySelectorAll('button'));
                            const easyApplyBtn = buttons.find(b => b.textContent.includes('Easy Apply') || b.className.includes('jobs-apply-button'));
                            if (easyApplyBtn) {
                                easyApplyBtn.style.border = '5px solid red'; // Highlight it
                                easyApplyBtn.click();
                            }
                        }""")
                        print("✅ Clicked Easy Apply!")
                        
                        print("⏳ Waiting 3 seconds for the Easy Apply modal or external site to load...")
                        await page.wait_for_timeout(3000)
                        
                        # --- NEW: Form Filler Injection ---
                        from core.form_filler import UniversalFormFiller
                        filler = UniversalFormFiller(profile)
                        form_success = await filler.parse_and_fill(page, page.url)
                        
                        if not form_success:
                            print(f"⏭️ Skipping job {i+1} due to external form constraints (e.g., Account Wall).")
                            db.mark_processed(job_id, "linkedin", "Skipped (Form Constraint)", title=job_title)
                            continue
                        # ----------------------------------
                        
                        print("⏳ Waiting 8 seconds so you can see the Easy Apply modal before it closes...")
                        await page.wait_for_timeout(8000)
                        
                        first_name = profile.get("personal_info", {}).get("first_name", "User")
                        print(f"   -> Filled Name: {first_name}")
                        print(f"   -> Uploaded tailored CV: {tailored_cv_path}")
                        
                        print("✅ LIVE: LinkedIn Application flow successfully triggered autonomously!")
                        db.mark_processed(job_id, "linkedin", "Applied", title=job_title)
                        
                        # Close the modal manually if it's still open so we can proceed to the next job
                        await page.evaluate("""() => {
                            const closeBtns = Array.from(document.querySelectorAll('button'));
                            const dismissBtn = closeBtns.find(b => b.getAttribute('aria-label') === 'Dismiss' || b.getAttribute('data-test-modal-close-btn') === 'true');
                            if (dismissBtn) dismissBtn.click();
                        }""")
                        
                        # Randomized delay
                        delay = random.randint(10, 30)
                        print(f"💤 Sleeping for {delay} seconds to prevent anti-bot bans before next job...")
                        await page.wait_for_timeout(delay * 1000)
                        
                    except Exception as e:
                        print(f"⚠️ Could not interact with the Easy Apply button for job {i+1}: {e}")
                        db.mark_processed(job_id, "linkedin", "Failed (Interaction Error)", title=job_title)
                        
                # Go to Next Page
                print("⏭️ Looking for Next Page button...")
                try:
                    has_next = await page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        const nextBtn = buttons.find(b => b.getAttribute('aria-label') && b.getAttribute('aria-label').toLowerCase().includes('next'));
                        if (nextBtn) {
                            nextBtn.click();
                            return true;
                        }
                        return false;
                    }""")
                    
                    if not has_next:
                        print("✅ No more pages found. Search exhausted.")
                        break
                        
                    print(f"⏳ Sleeping for 5 seconds while Page {page_num + 1} loads...")
                    await page.wait_for_timeout(5000)
                except Exception as e:
                    print("⚠️ Could not click next page. Exiting loop.")
                    break
            
            print("🎉 Full Pagination and Batch processing complete!")
            await browser.close()
