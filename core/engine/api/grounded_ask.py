"""HTTP transport for the governed grounded Ask and claim-bound correction surface."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from core.engine.core.auth import get_current_user
from core.engine.core.claim_bound_correction import (
    ClaimCorrectionAdmissionV1Alpha1,
    ClaimCorrectionHttpConflict,
    ClaimCorrectionHttpDenied,
    ClaimCorrectionHttpRequestV1,
    ClaimCorrectionHttpRuntime,
    ClaimCorrectionHttpUnauthenticated,
    ClaimCorrectionHttpUnavailable,
    claim_bound_correction_runtime,
    correct_claim_bound_ask_answer,
)
from core.engine.core.grounded_ask import (
    AskAnswerV1Alpha1,
    AskGroundedQuestionHttpConflict,
    AskGroundedQuestionHttpDenied,
    AskGroundedQuestionHttpRequestV1,
    AskGroundedQuestionHttpRuntime,
    AskGroundedQuestionHttpUnauthenticated,
    AskGroundedQuestionHttpUnavailable,
    AskNoAnswerV1Alpha1,
    ask_grounded_question,
    ask_grounded_question_runtime,
)

router = APIRouter(prefix="/v1/intelligence/ask", tags=["intelligence-ask"])


@router.post("", response_model=AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1)
async def ask_intelligence_question(
    selector: AskGroundedQuestionHttpRequestV1,
    user: dict = Depends(get_current_user),
    runtime: AskGroundedQuestionHttpRuntime = Depends(ask_grounded_question_runtime),
) -> AskAnswerV1Alpha1 | AskNoAnswerV1Alpha1:
    """Answer one question from authorized Brief claims, or refuse honestly."""

    try:
        return await ask_grounded_question(selector=selector, user=user, runtime=runtime)
    except AskGroundedQuestionHttpUnauthenticated as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except AskGroundedQuestionHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence ask denied") from exc
    except AskGroundedQuestionHttpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence ask evidence is unavailable",
        ) from exc
    except AskGroundedQuestionHttpConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Intelligence ask could not preserve its exact contract",
        ) from exc


@router.post(
    "/corrections",
    response_model=ClaimCorrectionAdmissionV1Alpha1,
    status_code=status.HTTP_201_CREATED,
)
async def create_claim_bound_correction(
    selector: ClaimCorrectionHttpRequestV1,
    user: dict = Depends(get_current_user),
    runtime: ClaimCorrectionHttpRuntime = Depends(claim_bound_correction_runtime),
) -> ClaimCorrectionAdmissionV1Alpha1:
    """Bind a correction to one exact claim/citation and record it as a proposal only."""

    try:
        return await correct_claim_bound_ask_answer(selector=selector, user=user, runtime=runtime)
    except ClaimCorrectionHttpUnauthenticated as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except ClaimCorrectionHttpDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Intelligence correction denied") from exc
    except ClaimCorrectionHttpUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Intelligence correction storage is unavailable",
        ) from exc
    except ClaimCorrectionHttpConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


__all__ = ["router"]
