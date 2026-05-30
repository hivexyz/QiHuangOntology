from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...dependencies import get_auth_service, get_current_user
from ...schemas import LoginRequest, SuccessEnvelope
from ...services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SuccessEnvelope)
def login(
    payload: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> SuccessEnvelope:
    data = auth_service.login(payload.email, payload.password)
    return SuccessEnvelope(trace_id=request.state.trace_id, data=data)


@router.get("/me", response_model=SuccessEnvelope)
def me(request: Request, user=Depends(get_current_user)) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=user)
