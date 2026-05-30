import json
import os
from pathlib import Path
from typing import List

import litellm

LITELLM_API_BASE = os.getenv("LITELLM_API_BASE", "https://shorthills.ai/litellm")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-1.5-flash")

PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text()


async def generate_test_cases(user_story: str, count: int = 10) -> List[dict]:
    prompt = _load_prompt("generate_test_cases.txt")
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"User story:\n{user_story}\n\nGenerate {count} test cases."},
    ]
    response = await litellm.acompletion(
        model=LLM_MODEL,
        messages=messages,
        api_base=LITELLM_API_BASE if LITELLM_API_BASE else None,
        api_key=LITELLM_API_KEY if LITELLM_API_KEY else None,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    return data.get("test_cases", [])


async def criticize_test_case(title: str, steps: str, expected_result: str) -> List[dict]:
    prompt = _load_prompt("criticize_test_case.txt")
    tc_text = f"Title: {title}\n\nSteps:\n{steps}\n\nExpected Result:\n{expected_result}"
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": tc_text},
    ]
    response = await litellm.acompletion(
        model=LLM_MODEL,
        messages=messages,
        api_base=LITELLM_API_BASE if LITELLM_API_BASE else None,
        api_key=LITELLM_API_KEY if LITELLM_API_KEY else None,
        response_format={"type": "json_object"},
        temperature=0.4,
    )
    content = response.choices[0].message.content
    data = json.loads(content)
    return data.get("suggestions", [])


async def generate_executive_summary(project_name: str, stats: dict) -> str:
    messages = [
        {
            "role": "user",
            "content": (
                f"Write a 2-sentence executive summary for project '{project_name}' QA report. "
                f"Stats: {stats['passed']} passed, {stats['failed']} failed, "
                f"{stats['coverage_pct']:.0f}% coverage. "
                "Be direct and professional. No fluff."
            ),
        }
    ]
    response = await litellm.acompletion(
        model=LLM_MODEL,
        messages=messages,
        api_base=LITELLM_API_BASE if LITELLM_API_BASE else None,
        api_key=LITELLM_API_KEY if LITELLM_API_KEY else None,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()
