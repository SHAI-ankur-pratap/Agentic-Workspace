import schedule
import time
import asyncio
from core.linkedin import LinkedInAgent
from core.naukri import NaukriAgent

class DaemonOrchestrator:
    def __init__(self, profile: dict, generator):
        self.profile = profile
        self.generator = generator

    def run_cycle(self):
        print("\n" + "="*50)
        print("🕒 [Orchestrator] Waking up for scheduled application cycle...")
        print("="*50)
        
        # Run LinkedIn
        try:
            linkedin = LinkedInAgent(headless=True)
            asyncio.run(linkedin.autonomous_search_and_apply(self.profile, self.generator))
        except Exception as e:
            print(f"❌ LinkedIn cycle failed: {e}")
            
        # Run Naukri
        try:
            naukri = NaukriAgent(headless=True)
            asyncio.run(naukri.autonomous_search_and_apply(self.profile, self.generator))
        except Exception as e:
            print(f"❌ Naukri cycle failed: {e}")
        
        print("\n💤 [Orchestrator] Cycle complete. Going back to sleep...")

    def start_daemon(self):
        print("🚀 [Orchestrator] 24/7 Agentic Loop Started!")
        print("ℹ️ The agent will run a cycle immediately, and then every 4 hours.")
        
        # Run first cycle immediately
        self.run_cycle()
        
        # Schedule every 4 hours
        schedule.every(4).hours.do(self.run_cycle)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n🛑 Daemon stopped by user.")
