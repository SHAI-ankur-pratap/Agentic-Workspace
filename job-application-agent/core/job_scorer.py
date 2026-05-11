import json
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from core.llm_helper import extract_text

load_dotenv()

SCORE_THRESHOLD = 6


class JobScorer:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-flash-latest",
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    def score(self, job_title: str, job_description: str, profile: dict) -> dict:
        roles = profile.get("preferences", {}).get("roles", [])
        skills = profile.get("skills", [])
        locations = profile.get("preferences", {}).get("locations", [])
        min_salary = profile.get("preferences", {}).get("minimum_salary", "")

        prompt = f"""Evaluate this job posting for a candidate. Score the match 0-10.

Candidate preferred roles: {', '.join(roles)}
Candidate skills: {', '.join(skills)}
Candidate location preferences: {', '.join(locations)}
Candidate minimum salary: {min_salary}

Job Title: {job_title}
Job Description: {job_description[:1500]}

Respond with ONLY valid JSON, no markdown fences:
{{"score": <0-10 integer>, "reason": "<one sentence>", "apply": <true if score>=6 else false>}}"""

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
