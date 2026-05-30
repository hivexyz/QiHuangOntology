from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ...dependencies import get_current_user, get_ontology_service
from ...schemas import OntologyImportCreateRequest, SuccessEnvelope
from ...services.ontology import OntologyService

router = APIRouter(prefix="/ontology", tags=["ontology"])


@router.post("/import-jobs", response_model=SuccessEnvelope)
def create_import_job(
    payload: OntologyImportCreateRequest,
    request: Request,
    _: object = Depends(get_current_user),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.create_import_job(payload))


@router.get("/import-jobs/{import_job_id}", response_model=SuccessEnvelope)
def get_import_job(
    import_job_id: UUID,
    request: Request,
    _: object = Depends(get_current_user),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_import_job(import_job_id))


@router.post("/import-jobs/{import_job_id}/publish", response_model=SuccessEnvelope)
def publish_import_job(
    import_job_id: UUID,
    request: Request,
    _: object = Depends(get_current_user),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.publish_import_job(import_job_id))


@router.get("/entities/{entity_id}", response_model=SuccessEnvelope)
def get_entity(
    entity_id: str,
    request: Request,
    _: object = Depends(get_current_user),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_entity(entity_id))


@router.get("/knowledge-cards/{entity_id}", response_model=SuccessEnvelope)
def get_knowledge_card(
    entity_id: str,
    request: Request,
    _: object = Depends(get_current_user),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_knowledge_card(entity_id))
