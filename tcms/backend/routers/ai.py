import logging
from typing import List

import litellm
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import llm as llm_module
from auth import get_current_user
from database import get_db
from models import Project, TestCase, User
from schemas import (
    CriticizeRequest,
    CriticizeResponse,
    GenerateRequest,
    GenerateResponse,
    GeneratedTestCase,
    Suggestion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

_AI_UNAVAILABLE = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="AI service unavailable, try again",
)


@router.post("/generate", response_model=GenerateResponse)
async def generate_test_cases(
    payload: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project_id = payload.project_id
    if project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    count = max(1, min(payload.count, 20))

    try:
        raw_cases = await llm_module.generate_test_cases(
            user_story=payload.user_story,
            count=count,
        )
    except litellm.exceptions.ServiceUnavailableError as exc:
        logger.warning("LLM service unavailable during generate: %s", exc)
        raise _AI_UNAVAILABLE
    except litellm.exceptions.APIConnectionError as exc:
        logger.warning("LLM connection error during generate: %s", exc)
        raise _AI_UNAVAILABLE
    except litellm.exceptions.RateLimitError as exc:
        logger.warning("LLM rate limit hit during generate: %s", exc)
        raise _AI_UNAVAILABLE
    except litellm.exceptions.AuthenticationError as exc:
        logger.error("LLM authentication error during generate: %s", exc)
        raise _AI_UNAVAILABLE
    except Exception as exc:
        logger.exception("Unexpected error during AI generate: %s", exc)
        raise _AI_UNAVAILABLE

    test_cases: List[GeneratedTestCase] = []
    for case in raw_cases:
        priority = case.get("priority", "P2").strip().upper()
        if priority not in {"P1", "P2", "P3", "P4"}:
            priority = "P2"
        test_cases.append(
            GeneratedTestCase(
                title=case.get("title", "").strip(),
                steps=case.get("steps", "").strip(),
                expected_result=case.get("expected_result", "").strip(),
                priority=priority,
            )
        )

    test_cases = [tc for tc in test_cases if tc.title]
    return GenerateResponse(test_cases=test_cases)


@router.post("/criticize", response_model=CriticizeResponse)
async def criticize_test_case(
    payload: CriticizeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    test_case = db.query(TestCase).filter(TestCase.id == payload.test_case_id).first()
    if not test_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test case not found",
        )

    try:
        raw_suggestions = await llm_module.criticize_test_case(
            title=test_case.title,
            steps=test_case.steps,
            expected_result=test_case.expected_result,
        )
    except litellm.exceptions.ServiceUnavailableError as exc:
        logger.warning("LLM service unavailable during criticize: %s", exc)
        raise _AI_UNAVAILABLE
    except litellm.exceptions.APIConnectionError as exc:
        logger.warning("LLM connection error during criticize: %s", exc)
        raise _AI_UNAVAILABLE
    except litellm.exceptions.RateLimitError as exc:
        logger.warning("LLM rate limit hit during criticize: %s", exc)
        raise _AI_UNAVAILABLE
    except litellm.exceptions.AuthenticationError as exc:
        logger.error("LLM auth error during criticize: %s", exc)
        raise _AI_UNAVAILABLE
    except Exception as exc:
        logger.exception("Unexpected error during AI criticize: %s", exc)
        raise _AI_UNAVAILABLE

    suggestions: List[Suggestion] = []
    for s in raw_suggestions:
        suggestions.append(
            Suggestion(
                type=s.get("type", "general"),
                description=s.get("description", ""),
                rewrite=s.get("rewrite"),
            )
        )

    return CriticizeResponse(suggestions=suggestions)
