class JobFilter:
    def __init__(self, profile: dict):
        self.profile = profile

    def score_job(self, job_title: str, job_description: str) -> dict:
        """Mock LLM scoring algorithm"""
        print(f"🧠 [Job Filter] Analyzing '{job_title}' against profile constraints...")
        
        score = 85 # Mock score
        passed = score >= 80
        reason = "Matches QA Lead seniority and mentions automation tools from your stack."
        
        print(f"   -> Score: {score}/100. {'✅ PASS' if passed else '❌ REJECT'}")
        print(f"   -> Reason: {reason}")
        
        return {
            "score": score,
            "passed": passed,
            "reason": reason
        }
