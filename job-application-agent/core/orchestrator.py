import schedule
import time
import asyncio
import threading
from core.linkedin import LinkedInAgent
from core.naukri import NaukriAgent


def _run_async(coro):
    """Run a coroutine in a fresh event loop in a new thread — safe from schedule callbacks."""
    result = {}

    def _thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result["stats"] = loop.run_until_complete(coro)
        except Exception as e:
            result["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=_thread)
    t.start()
    t.join()

    if "error" in result:
        raise result["error"]
    return result.get("stats", {})


class DaemonOrchestrator:
    def __init__(self, profile: dict, generator=None):
        self.profile = profile

    def run_cycle(self):
        print("\n" + "=" * 60)
        print("🕒 [Orchestrator] Starting application cycle...")
        print("=" * 60)

        totals = {"applied": 0, "skipped": 0, "failed": 0, "manual": 0}

        try:
            linkedin = LinkedInAgent(headless=True)
            stats = _run_async(linkedin.autonomous_search_and_apply(self.profile))
            for k in totals:
                totals[k] += stats.get(k, 0)
        except Exception as e:
            print(f"❌ LinkedIn cycle error: {e}")

        try:
            naukri = NaukriAgent(headless=True)
            stats = _run_async(naukri.autonomous_search_and_apply(self.profile))
            for k in totals:
                totals[k] += stats.get(k, 0)
        except Exception as e:
            print(f"❌ Naukri cycle error: {e}")

        print("\n" + "=" * 60)
        print(
            f"📊 Cycle complete → "
            f"✅ Applied: {totals['applied']} | "
            f"⏭ Skipped: {totals['skipped']} | "
            f"❌ Failed: {totals['failed']} | "
            f"📋 Manual: {totals['manual']}"
        )
        print("💤 Sleeping until next cycle (4 hours)...")
        print("=" * 60)

    def start_daemon(self):
        print("🚀 [Orchestrator] 24/7 Agentic Loop Started!")
        print("ℹ️ Running first cycle immediately, then every 4 hours.")
        self.run_cycle()
        schedule.every(4).hours.do(self.run_cycle)
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n🛑 Daemon stopped.")
