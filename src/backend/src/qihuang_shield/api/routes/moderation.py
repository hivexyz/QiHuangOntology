from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ...dependencies import get_moderation_service
from ...schemas import CreateBatchRequest, MetaInfo, ModerationSyncRequest, SuccessEnvelope
from ...services.moderation import ModerationService

router = APIRouter(prefix="/moderation", tags=["moderation"])


@router.post("/sync")
def moderate_sync(
    payload: ModerationSyncRequest,
    moderation_service: ModerationService = Depends(get_moderation_service),
):
    return moderation_service.moderate_sync(payload)


@router.post("/batches", response_model=SuccessEnvelope)
def create_batch(
    payload: CreateBatchRequest,
    request: Request,
    moderation_service: ModerationService = Depends(get_moderation_service),
) -> SuccessEnvelope:
    data = moderation_service.create_batch(payload)
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data)


@router.get("/batches/{batch_id}", response_model=SuccessEnvelope)
def get_batch_status(
    batch_id: UUID,
    request: Request,
    moderation_service: ModerationService = Depends(get_moderation_service),
) -> SuccessEnvelope:
    data = moderation_service.get_batch_status(batch_id)
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data)


@router.get("/batches/{batch_id}/items", response_model=SuccessEnvelope)
def get_batch_items(
    batch_id: UUID,
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    decision: str | None = Query(default=None),
    risk_level: str | None = Query(default=None),
    moderation_service: ModerationService = Depends(get_moderation_service),
) -> SuccessEnvelope:
    data, total = moderation_service.list_batch_items(batch_id, page, page_size, decision, risk_level)
    meta = MetaInfo(page=page, page_size=page_size, total=total, total_pages=max(1, (total + page_size - 1) // page_size))
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data, meta=meta)
