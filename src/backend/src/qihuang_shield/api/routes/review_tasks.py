from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ...dependencies import get_current_user, get_review_service
from ...schemas import ClaimReviewTaskRequest, FeedbackCreateRequest, MetaInfo, SubmitReviewTaskRequest, SuccessEnvelope
from ...services.review import ReviewService

router = APIRouter(prefix="/review-tasks", tags=["review_tasks"])


@router.get("", response_model=SuccessEnvelope)
def list_review_tasks(
    request: Request,
    status: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    rule_code: str | None = Query(default=None),
    scenario: str | None = Query(default=None),
    assignee_user_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: object = Depends(get_current_user),
    review_service: ReviewService = Depends(get_review_service),
) -> SuccessEnvelope:
    data, total, page, total_pages = review_service.list_tasks(
        page=page,
        page_size=page_size,
        status=status,
        risk_level=risk_level,
        rule_code=rule_code,
        scenario=scenario,
        assignee_user_id=assignee_user_id,
    )
    meta = MetaInfo(page=page, page_size=page_size, total=total, total_pages=total_pages)
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data, meta=meta)


@router.get("/{task_id}", response_model=SuccessEnvelope)
def get_review_task(
    task_id: UUID,
    request: Request,
    _: object = Depends(get_current_user),
    review_service: ReviewService = Depends(get_review_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=review_service.get_task(task_id))


@router.post("/{task_id}/claim", response_model=SuccessEnvelope)
def claim_review_task(
    task_id: UUID,
    payload: ClaimReviewTaskRequest,
    request: Request,
    _: object = Depends(get_current_user),
    review_service: ReviewService = Depends(get_review_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=review_service.claim_task(task_id, payload.operator_user_id))


@router.post("/{task_id}/submit", response_model=SuccessEnvelope)
def submit_review_task(
    task_id: UUID,
    payload: SubmitReviewTaskRequest,
    request: Request,
    _: object = Depends(get_current_user),
    review_service: ReviewService = Depends(get_review_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=review_service.submit_task(task_id, payload))


@router.post("/{task_id}/feedback", response_model=SuccessEnvelope)
def add_feedback(
    task_id: UUID,
    payload: FeedbackCreateRequest,
    request: Request,
    user=Depends(get_current_user),
    review_service: ReviewService = Depends(get_review_service),
) -> SuccessEnvelope:
    data = review_service.add_feedback(task_id, payload, user.user_id)
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data)
