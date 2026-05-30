from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ...dependencies import get_current_user, get_rule_service
from ...schemas import MetaInfo, RuleCreateRequest, RuleVersionCreateRequest, SuccessEnvelope
from ...services.rules import RuleService

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("", response_model=SuccessEnvelope)
def list_rules(
    request: Request,
    rule_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: object = Depends(get_current_user),
    rule_service: RuleService = Depends(get_rule_service),
) -> SuccessEnvelope:
    data, total, page, total_pages = rule_service.list_rules(page, page_size, rule_type, status, keyword)
    meta = MetaInfo(page=page, page_size=page_size, total=total, total_pages=total_pages)
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data, meta=meta)


@router.post("", response_model=SuccessEnvelope)
def create_rule(
    payload: RuleCreateRequest,
    request: Request,
    _: object = Depends(get_current_user),
    rule_service: RuleService = Depends(get_rule_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=rule_service.create_rule(payload))


@router.get("/{rule_id}", response_model=SuccessEnvelope)
def get_rule(
    rule_id: UUID,
    request: Request,
    _: object = Depends(get_current_user),
    rule_service: RuleService = Depends(get_rule_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=rule_service.get_rule(rule_id))


@router.post("/{rule_id}/versions", response_model=SuccessEnvelope)
def create_rule_version(
    rule_id: UUID,
    payload: RuleVersionCreateRequest,
    request: Request,
    _: object = Depends(get_current_user),
    rule_service: RuleService = Depends(get_rule_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=rule_service.create_rule_version(rule_id, payload))


@router.post("/{rule_id}/versions/{rule_version_id}/publish", response_model=SuccessEnvelope)
def publish_rule_version(
    rule_id: UUID,
    rule_version_id: UUID,
    request: Request,
    _: object = Depends(get_current_user),
    rule_service: RuleService = Depends(get_rule_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=rule_service.publish_rule_version(rule_id, rule_version_id))
