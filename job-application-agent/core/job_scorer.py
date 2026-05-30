import json
import os
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from core.llm_helper import extract_text
from core.llm_client import build_llm

load_dotenv()

SCORE_THRESHOLD = 3  # Apply broadly — include remotely related roles and career-adjacent opportunities


class JobScorer:
    def __init__(self):
        self.llm = build_llm(temperature=0)

    def score(self, job_title: str, job_description: str, profile: dict) -> dict:
        roles = profile.get("preferences", {}).get("roles", [])
        skills = profile.get("skills", [])
        locations = profile.get("preferences", {}).get("locations", [])
        min_salary = profile.get("preferences", {}).get("minimum_salary", "")

        prompt = f"""Evaluate this job posting for a candidate. Score 0-10 — be GENEROUS.

Apply broadly: include roles that are remotely related, adjacent to the candidate's career path,
or where their skills would transfer. Only score below 3 if the role is completely unrelated
(e.g. civil engineering for a software QA candidate).

Candidate preferred roles: {', '.join(roles)}
Candidate skills: {', '.join(skills)}
Candidate location preferences: {', '.join(locations)}
Candidate minimum salary: {min_salary}

Job Title: {job_title}
Job Description: {job_description[:1500]}

Scoring guide:
8-10: Strong direct match
5-7: Related role or transferable skills
3-4: Adjacent / career-path opportunity worth trying
1-2: Mostly unrelated but tiny overlap
0: Completely unrelated field

Respond with ONLY valid JSON, no markdown fences:
{{"score": <0-10 integer>, "reason": "<one sentence>", "apply": <true if score>=3 else false>}}"""

        for attempt in range(3):
            try:
                response = self.llm.invoke([HumanMessage(content=prompt)])
                text = extract_text(response.content).strip()
                if text.startswith("```"):
                    parts = text.split("```")
                    text = parts[1]
                    if text.startswith("json"):
                        text = text[4:]
                result = json.loads(text.strip())
                result["apply"] = int(result.get("score", 0)) >= SCORE_THRESHOLD
                return result
            except Exception as e:
                if attempt == 2:
                    print(f"⚠️ [Job Scorer] LLM failed: {e}. Defaulting apply=True.")
        return {"score": 5, "reason": "LLM unavailable, defaulting", "apply": True}
