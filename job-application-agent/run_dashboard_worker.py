import os
import sys
import yaml
import asyncio
import random
from pathlib import Path
from dotenv import load_dotenv

# Ensure the root of the worker is in sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from core.dashboard_client import DashboardClient
from core.linkedin import LinkedInAgent
from core.naukri import NaukriAgent

load_dotenv()

def load_profile(profile_path: str) -> dict:
    with open(profile_path, 'r') as f:
        return yaml.safe_load(f)

async def process_job(job: dict, profile: dict, default_resume: dict, client: DashboardClient) -> str:
    job_id = job["id"]
    url = job["url"]
    title = job["title"]
    company = job["company"]
    platform = job.get("platform", "other")
    
    print(f"\n🎯 [Dashboard Worker] Processing: {title} at {company} ({platform})")
    print(f"🔗 URL: {url}")
    
    # Notify dashboard that we are currently working on this job
    client.send_heartbeat(
        status="applying", 
        log_msg=f"Starting application: {title} at {company} ({platform})",
        metadata={"job_id": job_id, "title": title, "company": company}
    )
    
    outcome = "failed"
    error_msg = None
    
    try:
        if platform == "linkedin":
            agent = LinkedInAgent(headless=False)
            outcome = await agent.apply_to_job(url, profile)
        elif platform == "naukri":
            agent = NaukriAgent(headless=False)
            outcome = await agent.apply_to_job(url, profile)
        else:
            # For other platforms (lever, greenhouse, workday, etc.)
            from playwright.async_api import async_playwright
            from core.external_portal import ExternalPortalAgent
            from core.form_filler import UniversalFormFiller
            from core.cv_tailor import CVTailor
            
            print(f"🌐 Using External Portal Agent for '{company}'")
            async with async_playwright() as p:
                args = [
                    "--no-default-browser-check",
                    "--no-first-run",
                    "--disable-default-apps",
                    "--disable-fre",
                    "--disable-sync"
                ]
                chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                if os.path.exists(chrome_path):
                    browser = await p.chromium.launch(headless=False, executable_path=chrome_path, args=args)
                else:
                    browser = await p.chromium.launch(headless=False, args=args)
                    
                from core.browser import get_combined_storage_state
                combined = get_combined_storage_state()
                if combined and os.path.exists(combined):
                    print(f"🔓 Loading combined saved session: {combined}")
                    context = await browser.new_context(storage_state=combined)
                else:
                    context = await browser.new_context()
                page = await context.new_page()
                
                # Navigate to the external listing
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(3000)
                
                # Tailor CV for the description
                tailor = CVTailor()
                tailored_md = tailor.rewrite_cv(url)
                cv_path = "tailored_cv_external.pdf"
                await tailor.generate_pdf(tailored_md, cv_path)
                
                filler = UniversalFormFiller(profile)
                portal = ExternalPortalAgent(profile, filler)
                outcome = await portal.apply(page, url, cv_path)
                
                if os.path.exists(cv_path):
                    os.remove(cv_path)
                await browser.close()
                
    except Exception as e:
        outcome = "failed"
        error_msg = str(e)
        print(f"❌ Error applying: {e}")
        
    # Notify dashboard of the result
    resume_id = default_resume.get("id") if default_resume else None
    client.update_application(
        job_id=job_id,
        status=outcome,
        platform=platform,
        resume_id=resume_id,
        error=error_msg
    )
    
    return outcome

async def main():
    print("🚀 Starting Dashboard Worker Daemon...")
    
    # Load profile details
    profile_path = Path("profile.yaml")
    if not profile_path.exists():
        print(f"❌ Profile file not found at {profile_path}")
        return
    profile = load_profile(profile_path)
    
    # Setup dashboard config
    base_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
    token = os.getenv("WORKER_TOKEN", "").strip()
    
    if not token:
        print("❌ WORKER_TOKEN not found in environment or .env file.")
        print("Please fetch it from the Dashboard settings and configure it.")
        return
        
    print(f"📡 Dashboard URL: {base_url}")
    print(f"🔑 Worker Token: {token[:8]}...")
    
    client = DashboardClient(base_url, token, worker_name="apply")
    
    while True:
        try:
            state = client.get_state()
            if not state:
                print("💤 Failed to get state. Retrying in 30 seconds...")
                await asyncio.sleep(30)
                continue
                
            paused = state.get("paused", False)
            if paused:
                print("⏸️ Worker is PAUSED in dashboard settings. Sleeping...")
                client.send_heartbeat(status="paused", log_msg="Worker paused from settings dashboard")
                await asyncio.sleep(60)
                continue
                
            queue = state.get("queue", [])
            remaining = state.get("remaining", 0)
            
            print(f"📡 Heartbeat: OK | Queue Size: {len(queue)} | Daily Remaining Cap: {remaining}")
            client.send_heartbeat(
                status="idle", 
                log_msg=f"Worker active. Queue size: {len(queue)}",
                metadata={"queue_size": len(queue), "remaining": remaining}
            )
            
            if len(queue) > 0 and remaining > 0:
                # Select/update base resume content
                resumes = state.get("resumes", [])
                default_resume = None
                for r in resumes:
                    if r.get("is_default"):
                        default_resume = r
                        break
                if not default_resume and resumes:
                    default_resume = resumes[0]
                    
                if default_resume:
                    print(f"📄 Syncing default resume persona: '{default_resume.get('persona')}'")
                    with open("base_resume.md", "w") as f:
                        f.write(default_resume.get("content", ""))
                        
                # Process the first job in the queue
                job = queue[0]
                outcome = await process_job(job, profile, default_resume, client)
                print(f"🏁 Finished job with outcome: {outcome}")
                
                # Sleep between applications
                delay = random.randint(15, 30)
                print(f"💤 Sleeping for {delay} seconds before next run...")
                await asyncio.sleep(delay)
            else:
                # No jobs or cap reached
                await asyncio.sleep(45)
                
        except KeyboardInterrupt:
            print("\n🛑 Stop signal received. Exiting...")
            break
        except Exception as e:
            print(f"⚠️ Unexpected daemon error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
