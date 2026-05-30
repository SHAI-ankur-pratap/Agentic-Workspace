from core.job_scorer import JobScorer


class JobFilter:
    def __init__(self, profile: dict):
        self.profile = profile
        self._scorer = JobScorer()

    def score_job(self, job_title: str, job_description: str) -> dict:
        print(f"🧠 [Job Filter] Scoring '{job_title}'...")
        result = self._scorer.score(job_title, job_description, self.profile)
        passed = result.get("apply", True)
        score_10 = result.get("score", 5)
        print(f"   → Score: {score_10}/10 — {'✅ PASS' if passed else '❌ SKIP'}: {result.get('reason', '')}")
        return {"score": score_10 * 10, "passed": passed, "reason": result.get("reason", "")}
