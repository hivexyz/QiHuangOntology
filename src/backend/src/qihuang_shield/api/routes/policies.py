from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ...dependencies import get_current_user, get_policy_service
from ...schemas import MetaInfo, PolicyCreateRequest, PolicyVersionCreateRequest, SuccessEnvelope
from ...services.policies import PolicyService

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=SuccessEnvelope)
def list_policies(
    request: Request,
    tenant_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    policy_code: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    _: object = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> SuccessEnvelope:
    data, total, page, total_pages = policy_service.list_policies(page, page_size, tenant_id, status, policy_code, keyword)
    meta = MetaInfo(page=page, page_size=page_size, total=total, total_pages=total_pages)
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data, meta=meta)


@router.post("", response_model=SuccessEnvelope)
def create_policy(
    payload: PolicyCreateRequest,
    request: Request,
    _: object = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=policy_service.create_policy(payload))


@router.get("/{policy_id}", response_model=SuccessEnvelope)
def get_policy(
    policy_id: UUID,
    request: Request,
    _: object = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=policy_service.get_policy(policy_id))


@router.post("/{policy_id}/versions", response_model=SuccessEnvelope)
def create_policy_version(
    policy_id: UUID,
    payload: PolicyVersionCreateRequest,
    request: Request,
    _: object = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=policy_service.create_policy_version(policy_id, payload))


@router.post("/{policy_id}/versions/{policy_version_id}/publish", response_model=SuccessEnvelope)
def publish_policy_version(
    policy_id: UUID,
    policy_version_id: UUID,
    request: Request,
    _: object = Depends(get_current_user),
    policy_service: PolicyService = Depends(get_policy_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=policy_service.publish_policy_version(policy_id, policy_version_id))
