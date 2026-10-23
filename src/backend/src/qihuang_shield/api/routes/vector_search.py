from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...dependencies import get_vector_search_service, require_permission
from ...schemas import SuccessEnvelope, VectorSearchRequest, VectorUpsertRequest
from ...services.vector_search import VectorSearchService

router = APIRouter(prefix="/vector-search", tags=["vector-search"])


@router.get("/health", response_model=SuccessEnvelope)
def vector_health(
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    service: VectorSearchService = Depends(get_vector_search_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=service.health())


@router.post("/documents", response_model=SuccessEnvelope)
def upsert_document(
    payload: VectorUpsertRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "write")),
    service: VectorSearchService = Depends(get_vector_search_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=service.upsert_text(doc_id=payload.doc_id, text=payload.text, metadata=payload.metadata))


@router.post("/query", response_model=SuccessEnvelope)
def query_vectors(
    payload: VectorSearchRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    service: VectorSearchService = Depends(get_vector_search_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=service.semantic_search(query=payload.query, top_k=payload.top_k))


@router.post("/rag-query", response_model=SuccessEnvelope)
def rag_query(
    payload: VectorSearchRequest,
    request: Request,
    _: object = Depends(require_permission("ontology", "read")),
    service: VectorSearchService = Depends(get_vector_search_service),
) -> SuccessEnvelope:
    return SuccessEnvelope(trace_id=request.state.trace_id, data=service.rag_search(query=payload.query, top_k=payload.top_k))
