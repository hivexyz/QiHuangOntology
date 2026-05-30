from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...dependencies import get_current_user, get_report_service
from ...schemas import SuccessEnvelope
from ...services.reports import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/overview", response_model=SuccessEnvelope)
def overview(
    request: Request,
    _: object = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=report_service.overview())


@router.get("/rule-hits", response_model=SuccessEnvelope)
def rule_hits(
    request: Request,
    _: object = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=report_service.rule_hits())


@router.get("/review-quality", response_model=SuccessEnvelope)
def review_quality(
    request: Request,
    _: object = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=report_service.review_quality())
