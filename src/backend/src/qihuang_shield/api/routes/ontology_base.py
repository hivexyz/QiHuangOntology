from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request

from ...dependencies import get_ontology_base_service, get_ontology_base_validator, require_permission
from ...exceptions import APIError
from ...schemas import SuccessEnvelope
from ...services.ontology_base import OntologyBaseService

router = APIRouter(prefix="/ontology-base", tags=["ontology-base"])


@router.get("/validate", response_model=SuccessEnvelope)
def validate_ontology_base(
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_validator = Depends(get_ontology_base_validator),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_validator.validate())


@router.get("/concepts", response_model=SuccessEnvelope)
def list_concepts(
    request: Request,
    concept_type: str | None = Query(default=None),
    kb_version: str | None = Query(default=None),
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.list_concepts(concept_type=concept_type, kb_version=kb_version),
    )


@router.get("/concept-search", response_model=SuccessEnvelope)
def search_concepts(
    request: Request,
    query: str = Query(..., min_length=1),
    concept_type: str | None = Query(default=None),
    kb_version: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.search_concepts(
            query=query,
            concept_type=concept_type,
            kb_version=kb_version,
            limit=limit,
        ),
    )


@router.get("/concepts/{concept_id}", response_model=SuccessEnvelope)
def get_concept(
    concept_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_concept(concept_id))


@router.get("/concepts/{concept_id}/verification", response_model=SuccessEnvelope)
def get_concept_verification(
    concept_id: str,
    request: Request,
    kb_version: str | None = Query(default=None),
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.get_concept_verification(concept_id, kb_version=kb_version),
    )


@router.get("/assertions", response_model=SuccessEnvelope)
def list_assertions(
    request: Request,
    predicate_type: str | None = Query(default=None),
    subject_entity_id: str | None = Query(default=None),
    object_entity_id: str | None = Query(default=None),
    kb_version: str | None = Query(default=None),
    condition_context_json: str | None = Query(default=None),
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    condition_context = _parse_condition_context(condition_context_json)
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.list_assertions(
            predicate_type=predicate_type,
            subject_entity_id=subject_entity_id,
            object_entity_id=object_entity_id,
            kb_version=kb_version,
            condition_context=condition_context,
        ),
    )


def _parse_condition_context(condition_context_json: str | None) -> dict[str, object] | None:
    if not condition_context_json:
        return None
    try:
        parsed = json.loads(condition_context_json)
    except json.JSONDecodeError as exc:
        raise APIError(
            status_code=400,
            code="invalid_condition_context",
            message="condition_context_json must be valid JSON",
        ) from exc
    if not isinstance(parsed, dict):
        raise APIError(
            status_code=400,
            code="invalid_condition_context",
            message="condition_context_json must decode to an object",
        )
    return parsed


@router.get("/versions", response_model=SuccessEnvelope)
def list_versions(
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.list_versions())


@router.get("/versions/{version_id}", response_model=SuccessEnvelope)
def get_version(
    version_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_version(version_id))


@router.get("/releases", response_model=SuccessEnvelope)
def list_releases(
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.list_releases())


@router.get("/releases/{release_id}", response_model=SuccessEnvelope)
def get_release(
    release_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_release(release_id))


@router.get("/releases/{release_id}/diff", response_model=SuccessEnvelope)
def get_release_diff(
    release_id: str,
    request: Request,
    base_release_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.get_release_diff(
            release_id,
            base_release_id=base_release_id,
            limit=limit,
        ),
    )


@router.get("/objects/{object_id}/timeline", response_model=SuccessEnvelope)
def get_object_timeline(
    object_id: str,
    request: Request,
    object_type: str | None = Query(default=None),
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.get_object_timeline(object_id, object_type=object_type),
    )


@router.get("/relations", response_model=SuccessEnvelope)
def list_relation_definitions(
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.list_relation_definitions())


@router.get("/relations/{relation_code}", response_model=SuccessEnvelope)
def get_relation_definition(
    relation_code: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_relation_definition(relation_code))




@router.get("/concepts/{concept_id}/bundle", response_model=SuccessEnvelope)
def get_concept_bundle(
    concept_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.get_concept_bundle(concept_id),
    )


@router.get("/concepts/{concept_id}/assertions", response_model=SuccessEnvelope)
def list_assertions_for_concept(
    concept_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.list_assertions_for_concept(concept_id),
    )


@router.get("/assertions/{assertion_id}/evidence", response_model=SuccessEnvelope)
def list_evidence_for_assertion(
    assertion_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.list_evidence_for_assertion(assertion_id),
    )


@router.get("/assertions/{assertion_id}/condition", response_model=SuccessEnvelope)
def get_condition_for_assertion(
    assertion_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.get_condition_for_assertion(assertion_id),
    )

@router.get("/assertions/{assertion_id}/bundle", response_model=SuccessEnvelope)
def get_assertion_bundle(
    assertion_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_base_service.get_assertion_bundle(assertion_id),
    )


@router.get("/assertions/{assertion_id}", response_model=SuccessEnvelope)
def get_assertion(
    assertion_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_assertion(assertion_id))


@router.get("/conditions/{condition_set_id}", response_model=SuccessEnvelope)
def get_condition_set(
    condition_set_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_condition_set(condition_set_id))


@router.get("/evidence-links/{link_id}", response_model=SuccessEnvelope)
def get_evidence_link(
    link_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_evidence_link(link_id))


@router.get("/change-records/{change_id}", response_model=SuccessEnvelope)
def get_change_record(
    change_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_base_service: OntologyBaseService = Depends(get_ontology_base_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_base_service.get_change_record(change_id))
