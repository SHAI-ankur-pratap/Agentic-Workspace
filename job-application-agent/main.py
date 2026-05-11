import argparse
import os
import yaml
import asyncio
from pathlib import Path
from core.generator import ApplicationGenerator
from core.linkedin import LinkedInAgent
from core.naukri import NaukriAgent
from core.orchestrator import DaemonOrchestrator

def load_profile(profile_path: str) -> dict:
    with open(profile_path, 'r') as f:
        return yaml.safe_load(f)

async def async_main(args, profile):
    first_name = profile.get('personal_info', {}).get('first_name', 'User')
    print(f"✅ Loaded profile for {first_name}")
    
    # Initialize Generator
    generator = ApplicationGenerator()
    
    if args.daemon:
        orchestrator = DaemonOrchestrator(profile, generator)
        orchestrator.start_daemon()
        return

    # Select Agent
    if args.platform == "linkedin":
        agent = LinkedInAgent(headless=False)
    elif args.platform == "naukri":
        agent = NaukriAgent(headless=False)
    else:
        print("❌ Unsupported platform.")
        return

    if args.autonomous:
        print(f"🔥 Starting FULLY AUTONOMOUS Agentic Process for {args.platform.capitalize()}...")
        await agent.autonomous_search_and_apply(profile, generator)
        return

    # Handle Login Mode
    if args.login:
        await agent.login_and_save_state(agent.login_url)
        return

    # Handle Application Mode
    if args.url:
        print(f"🎯 Target {args.platform.capitalize()} Job URL: {args.url}")
        
        if args.mode == "apply":
            print("🚀 Commencing Application Process...")
            await agent.apply_to_job(args.url, profile, generator)
            print("✅ Application process finished.")
        else:
            print("ℹ️ Dry-run mode. Skipping browser automation.")

def main():
    parser = argparse.ArgumentParser(description="Automated Job Application Agent")
    parser.add_argument("--profile", default="profile.yaml", help="Path to profile.yaml")
    parser.add_argument("--mode", choices=["dry-run", "apply"], default="dry-run", help="Execution mode")
    parser.add_argument("--platform", choices=["linkedin", "naukri"], default="linkedin", help="Target job platform")
    parser.add_argument("--url", help="Specific job posting URL to apply to")
    parser.add_argument("--login", action="store_true", help="Launch browser to manually log in and save session cookies")
    parser.add_argument("--autonomous", action="store_true", help="Run the fully agentic process: Auto-login, auto-search, and auto-apply")
    parser.add_argument("--daemon", action="store_true", help="Run 24/7 round the clock orchestration across all platforms")
    args = parser.parse_args()

    print("🚀 Starting Job Application Agent...")
    
    profile_path = Path(args.profile)
    if not profile_path.exists():
        print(f"❌ Profile file not found at {profile_path}")
        return
        
    profile = load_profile(profile_path)
    
    asyncio.run(async_main(args, profile))

if __name__ == "__main__":
    main()
