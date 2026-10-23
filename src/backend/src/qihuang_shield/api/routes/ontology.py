from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from ...dependencies import get_config_service, get_ontology_service, require_permission
from ...schemas import (
    ConceptAliasReviewRequest,
    ConceptProposalCreateRequest,
    ConceptProposalReviewRequest,
    NormalizationDecisionBatchReviewRequest,
    NormalizationDecisionReviewRequest,
    OntologyImportCreateRequest,
    StagedAssertionReviewRequest,
    SuccessEnvelope,
    TerminologyPublishRequest,
)
from ...services.ontology import OntologyService

router = APIRouter(prefix="/ontology", tags=["ontology"])


@router.post("/import-jobs", response_model=SuccessEnvelope)
def create_import_job(
    payload: OntologyImportCreateRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.create_import_job(payload))


@router.post("/guideline-imports", response_model=SuccessEnvelope)
def import_guideline(
    payload: OntologyImportCreateRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.import_guideline(payload))


@router.get("/import-jobs/{import_job_id}", response_model=SuccessEnvelope)
def get_import_job(
    import_job_id: UUID,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_import_job(import_job_id))


@router.get("/import-jobs/{import_job_id}/governance", response_model=SuccessEnvelope)
def get_import_governance(
    import_job_id: UUID,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.get_import_governance(import_job_id),
    )


@router.post("/import-jobs/{import_job_id}/publish", response_model=SuccessEnvelope)
def publish_import_job(
    import_job_id: UUID,
    request: Request,
    _: object = Depends(require_permission("ontology", "publish")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.publish_import_job(import_job_id))


@router.post("/import-jobs/{import_job_id}/normalizations/{decision_id}/review", response_model=SuccessEnvelope)
def review_staged_normalization_decision(
    import_job_id: UUID,
    decision_id: str,
    payload: NormalizationDecisionReviewRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.review_staged_normalization_decision(import_job_id, decision_id, payload),
    )


@router.post("/import-jobs/{import_job_id}/assertions/{assertion_id}/review", response_model=SuccessEnvelope)
def review_staged_assertion(
    import_job_id: UUID,
    assertion_id: str,
    payload: StagedAssertionReviewRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.review_staged_assertion(import_job_id, assertion_id, payload),
    )


@router.post(
    "/import-jobs/{import_job_id}/normalizations/{decision_id}/concept-proposals",
    response_model=SuccessEnvelope,
)
def create_concept_proposal(
    import_job_id: UUID,
    decision_id: str,
    payload: ConceptProposalCreateRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.create_concept_proposal(import_job_id, decision_id, payload),
    )


@router.get("/import-jobs/{import_job_id}/concept-proposals", response_model=SuccessEnvelope)
def list_concept_proposals(
    import_job_id: UUID,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.list_concept_proposals(import_job_id),
    )


@router.post(
    "/import-jobs/{import_job_id}/concept-proposals/{proposal_id}/review",
    response_model=SuccessEnvelope,
)
def review_concept_proposal(
    import_job_id: UUID,
    proposal_id: str,
    payload: ConceptProposalReviewRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.review_concept_proposal(import_job_id, proposal_id, payload),
    )


@router.get("/entities/{entity_id}", response_model=SuccessEnvelope)
def get_entity(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_entity(entity_id))


@router.get("/diseases/{entity_id}", response_model=SuccessEnvelope)
def get_disease_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_disease_detail(entity_id))


@router.get("/symptoms/{entity_id}", response_model=SuccessEnvelope)
def get_symptom_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_symptom_detail(entity_id))


@router.get("/patterns/{entity_id}", response_model=SuccessEnvelope)
def get_pattern_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_pattern_detail(entity_id))


@router.get("/formulas/{entity_id}", response_model=SuccessEnvelope)
def get_formula_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_formula_detail(entity_id))


@router.get("/herbs/{entity_id}", response_model=SuccessEnvelope)
def get_herb_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_herb_detail(entity_id))


@router.get("/treatment-methods/{entity_id}", response_model=SuccessEnvelope)
def get_treatment_method_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_treatment_method_detail(entity_id))


@router.get("/treatment-principles/{entity_id}", response_model=SuccessEnvelope)
def get_treatment_principle_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_treatment_principle_detail(entity_id))


@router.get("/knowledge-cards/{entity_id}", response_model=SuccessEnvelope)
def get_knowledge_card(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_knowledge_card(entity_id))


@router.get("/projections/knowledge-cards/{entity_id}", response_model=SuccessEnvelope)
def get_knowledge_card_projection(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_projection_detail(entity_id))


@router.get("/projections/{entity_id}", response_model=SuccessEnvelope)
def get_projection_detail(
    entity_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_projection_detail(entity_id))


@router.get("/mentions/{mention_id}", response_model=SuccessEnvelope)
def get_mention(
    mention_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_mention(mention_id))


@router.get("/normalizations", response_model=SuccessEnvelope)
def list_normalization_decisions(
    request: Request,
    status: str | None = None,
    kb_version: str | None = None,
    source_type: str | None = None,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.list_normalization_decisions(
            status=status,
            kb_version=kb_version,
            source_type=source_type,
        ),
    )


@router.post("/normalizations/batch-review", response_model=SuccessEnvelope)
def batch_review_normalization_decisions(
    payload: NormalizationDecisionBatchReviewRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.batch_review_normalization_decisions(payload),
    )


@router.get("/normalizations/{decision_id}", response_model=SuccessEnvelope)
def get_normalization_decision(
    decision_id: str,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=ontology_service.get_normalization_decision(decision_id))


@router.post("/normalizations/{decision_id}/review", response_model=SuccessEnvelope)
def review_normalization_decision(
    decision_id: str,
    payload: NormalizationDecisionReviewRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.review_normalization_decision(decision_id, payload),
    )


@router.post("/concept-aliases/{alias_id}/review", response_model=SuccessEnvelope)
def review_concept_alias(
    alias_id: str,
    payload: ConceptAliasReviewRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.review_concept_alias(alias_id, payload),
    )


@router.post("/terminology/versions/publish", response_model=SuccessEnvelope)
def publish_terminology_version(
    payload: TerminologyPublishRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "publish")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.publish_terminology_version(payload),
    )


@router.post("/terminology/versions/{version_id}/rollback", response_model=SuccessEnvelope)
def rollback_terminology_version(
    version_id: str,
    request: Request,
    operator_id: str = "system",
    _: object = Depends(require_permission("ontology", "publish")),
    ontology_service: OntologyService = Depends(get_ontology_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(
        trace_id=request.state.trace_id,
        data=ontology_service.rollback_terminology_version(version_id, operator_id=operator_id),
    )


@router.get("/config-check", response_model=SuccessEnvelope)
def get_config_check(
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    config_service=Depends(get_config_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=config_service.health_snapshot())
