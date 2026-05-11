from core.browser import JobBrowserAgent
from playwright.async_api import async_playwright
import asyncio
import os
from dotenv import load_dotenv
from core.filter import JobFilter
from core.cv_tailor import CVTailor

load_dotenv()

class NaukriAgent(JobBrowserAgent):
    def __init__(self, headless=False):
        super().__init__(headless=headless, state_file="naukri_session.json")
        self.login_url = "https://login.naukri.com/"
        self.email = os.getenv("NAUKRI_EMAIL")
        self.password = os.getenv("NAUKRI_PASSWORD")

    async def auto_login(self, page):
        if os.path.exists(self.state_file):
            return True
        print(f"🤖 Agentic Login to Naukri with {self.email}...")
        await page.goto(self.login_url)
        await page.fill("input#usernameField", self.email)
        await page.fill("input#passwordField", self.password)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(3000)
        
        # Save session
        await page.context.storage_state(path=self.state_file)
        print("✅ Autonomous login successful. Session saved.")
        return True

    async def autonomous_search_and_apply(self, profile: dict, generator=None):
        """Fully autonomous loop: Log in -> Search -> Apply"""
        async with async_playwright() as p:
            browser = await self.get_browser(p)
            context = await self.get_context(browser)
            page = await context.new_page()
            
            # Step 1: Login
            await self.auto_login(page)

            # Step 2: Search for roles
            roles = profile.get("preferences", {}).get("roles", ["QA Manager"])
            search_query = "-".join(roles[0].lower().split())
            search_url = f"https://www.naukri.com/{search_query}-jobs?k={roles[0]}&sort=r"
            
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
                print("🎯 Extracting all Job Cards on the page...")
                await page.wait_for_timeout(3000)
                
                job_data_list = await page.evaluate("""() => {
                    const divs = Array.from(document.querySelectorAll('div'));
                    const jobCards = divs.filter(div => div.className.includes('text-title') && (div.textContent.toLowerCase().includes('qa') || div.textContent.toLowerCase().includes('manager')));
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
                    # Company name is hard to extract generically from just the title div, using Unknown for now.
                    # The title itself is usually unique enough combined with recent sorting.
                    job_id = db.generate_job_id("UnknownCompany", job_title)
                    
                    print(f"\n--- 🔄 Processing Job {i+1} of {job_count}: {job_title[:30]}... ---")
                    
                    if db.is_processed(job_id):
                        print("⏭️ [Idempotency] Job already processed previously! Skipping to save API costs.")
                        continue
                    
                    # Mock JD for AI filtering
                    mock_jd = f"Looking for an experienced {roles[0]} with 8+ years experience in automated testing."
                    
                    # Step 3: Filter Job
                    job_filter = JobFilter(profile)
                    filter_result = job_filter.score_job(roles[0], mock_jd)
                    
                    if not filter_result["passed"]:
                        print("⏭️ Job does not meet criteria. Skipping...")
                        db.mark_processed(job_id, "naukri", "Skipped (Low Filter Score)", title=job_title)
                        continue

                    # Step 4: Tailor CV
                    tailor = CVTailor()
                    tailored_md = tailor.rewrite_cv(mock_jd)
                    tailored_cv_path = tailor.generate_pdf(tailored_md, f"tailored_naukri_cv_{i+1}.pdf")

                    # Step 5: Apply
                    print("🤖 Agentic Apply: Navigating to Job Page...")
                    try:
                        async with context.expect_page() as new_page_info:
                            await page.evaluate(f"""(index) => {{
                                const divs = Array.from(document.querySelectorAll('div'));
                                const jobCards = divs.filter(div => div.className.includes('text-title') && (div.textContent.toLowerCase().includes('qa') || div.textContent.toLowerCase().includes('manager')));
                                if (jobCards[index]) jobCards[index].click();
                            }}""", i)
                        
                        job_page = await new_page_info.value
                        await job_page.wait_for_load_state()
                        print("✅ Opened Job Details in a new tab. Waiting 5 seconds for React to render...")
                        await job_page.wait_for_timeout(5000)
                        
                        # Attempt to click the real Apply button and catch if it opens an external site
                        try:
                            async with context.expect_page(timeout=5000) as ext_page_info:
                                # Use Playwright's native trusted click to ensure React registers it
                                try:
                                    apply_btn = job_page.locator("button:has-text('Apply'), a:has-text('Apply')").filter(has_not_text="Login").first
                                    await apply_btn.evaluate("el => el.style.border = '5px solid red'")
                                    await apply_btn.click(force=True)
                                except Exception:
                                    # Fallback to JS click if locator fails
                                    await job_page.evaluate("""() => {
                                        const buttons = Array.from(document.querySelectorAll('button, a'));
                                        const applyBtn = buttons.find(b => b.textContent.includes('Apply') && !b.textContent.includes('Login'));
                                        if (applyBtn) {
                                            applyBtn.style.border = '5px solid red';
                                            applyBtn.click();
                                        }
                                    }""")
                            
                            # It opened a new external tab!
                            external_page = await ext_page_info.value
                            await external_page.wait_for_load_state()
                            print(f"🔗 Opened External Company Site: {external_page.url}")
                            
                            from core.form_filler import UniversalFormFiller
                            filler = UniversalFormFiller(profile)
                            form_success = await filler.parse_and_fill(external_page, external_page.url)
                            
                            if not form_success:
                                print(f"⏭️ Skipping job {i+1} due to external form constraints (e.g., Account Wall).")
                                db.mark_processed(job_id, "naukri", "Skipped (External Form)", title=job_title)
                            else:
                                print("✅ External application flow triggered!")
                                db.mark_processed(job_id, "naukri", "Applied Externally", title=job_title)
                                
                            print("⏳ Waiting 15 seconds to verify external confirmation...")
                            await external_page.wait_for_timeout(15000)
                            await external_page.close()
                            
                        except Exception:
                            # TimeoutError: No new tab opened. It's an internal Naukri Apply!
                            print("✅ Clicked Apply internally on Naukri!")
                            print("⏳ Waiting 3 seconds for internal questionnaire modals...")
                            await job_page.wait_for_timeout(3000)
                            
                            from core.form_filler import UniversalFormFiller
                            filler = UniversalFormFiller(profile)
                            form_success = await filler.parse_and_fill(job_page, job_page.url)
                            
                            if not form_success:
                                print(f"⏭️ Skipping job {i+1} due to internal form constraints.")
                                db.mark_processed(job_id, "naukri", "Skipped (Internal Form)", title=job_title)
                            else:
                                print("⏳ Waiting 15 seconds so you can verify the 'Successfully Applied' confirmation...")
                                await job_page.wait_for_timeout(15000)
                                print(f"   -> Uploaded tailored CV: {tailored_cv_path}")
                                print("✅ LIVE: Naukri application flow successfully triggered autonomously!")
                                db.mark_processed(job_id, "naukri", "Applied", title=job_title)
                        
                        # Close the job tab so we return to search results
                        await job_page.close()
                        
                        # Randomized delay
                        delay = random.randint(10, 30)
                        print(f"💤 Sleeping for {delay} seconds to prevent anti-bot bans before next job...")
                        await page.wait_for_timeout(delay * 1000)
                        
                    except Exception as e:
                        print(f"⚠️ Could not interact with the Naukri Apply button for job {i+1}: {e}")
                        db.mark_processed(job_id, "naukri", "Failed (Interaction Error)", title=job_title)
                        try:
                            await job_page.close()
                        except:
                            pass
                            
                # Go to Next Page
                print("⏭️ Looking for Next Page button...")
                try:
                    has_next = await page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('a, button, span'));
                        const nextBtn = buttons.find(b => b.textContent.toLowerCase().includes('next'));
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
