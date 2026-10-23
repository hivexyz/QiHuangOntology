from __future__ import annotations

from collections import Counter
from copy import deepcopy
from uuid import UUID, uuid4

from ..config import get_settings
from ..exceptions import APIError
from ..schemas import (
    AssertionBundleView,
    ChangeRecordView,
    ConceptAliasReviewRequest,
    ConceptProposalCreateRequest,
    ConceptProposalReviewRequest,
    ConceptProposalView,
    ConditionSetView,
    EvidenceSourceView,
    GuidelineDocumentView,
    ImportGovernanceIssueView,
    ImportGovernanceSummaryView,
    ImportGovernanceView,
    KnowledgeCard,
    KnowledgeCardDetail,
    MentionView,
    NormalizationDecisionBatchReviewRequest,
    NormalizationDecisionReviewRequest,
    NormalizationDecisionView,
    OntologyConceptDetail,
    OntologyAssertionView,
    OntologyEntityView,
    OntologyImportCreateRequest,
    OntologyImportJobView,
    OntologyVersionView,
    StagedAssertionReviewRequest,
    TerminologyPublishRequest,
)
from ..store import InMemoryStore
from ..utils import utcnow
from .guideline_import import GuidelineOntologyExtractor
from .guideline_llm import GuidelineLLMExtractor
from .ontology_base_validator import ALLOWED_ONTOLOGY_TYPES, OntologyBaseValidator
from .owl_import import OwlOntologyImporter
from .terminology import StoreTerminologyResolver
from .vector_search import VectorSearchService


OWL_SOURCE_TYPES = {"owl", "rdf", "ttl", "turtle", "jsonld", "json-ld"}


class OntologyService:
    def __init__(self, store: InMemoryStore, vector_search_service: VectorSearchService | None = None) -> None:
        self.store = store
        self.guideline_extractor = GuidelineOntologyExtractor(StoreTerminologyResolver(store))
        self.guideline_llm_extractor = GuidelineLLMExtractor(get_settings(), self.guideline_extractor)
        self.vector_search_service = vector_search_service

    def _stage_bundle_on_job(self, job: dict, bundle: object) -> None:
        job["staged_snapshot"] = {
            "ontology_entities": deepcopy(getattr(bundle, "ontology_entities", {}) or {}),
            "ontology_assertions": deepcopy(getattr(bundle, "ontology_assertions", {}) or {}),
            "evidence_sources": deepcopy(getattr(bundle, "evidence_sources", {}) or {}),
            "concept_aliases": deepcopy(getattr(bundle, "concept_aliases", {}) or {}),
            "guideline_documents": deepcopy(getattr(bundle, "guideline_documents", {}) or {}),
            "mentions": deepcopy(getattr(bundle, "mentions", {}) or {}),
            "normalization_decisions": deepcopy(getattr(bundle, "normalization_decisions", {}) or {}),
            "concept_proposals": {},
            "condition_sets": deepcopy(getattr(bundle, "condition_sets", {}) or {}),
        }

    def _build_staged_validation_store(self, staged_snapshot: dict) -> InMemoryStore:
        validation_store = InMemoryStore(seed_demo_data=False)
        for field_name in (
            "ontology_entities",
            "ontology_assertions",
            "evidence_sources",
            "concept_aliases",
            "guideline_documents",
            "mentions",
            "normalization_decisions",
            "knowledge_card_projections",
            "ontology_versions",
            "relation_definitions",
            "condition_sets",
            "evidence_links",
            "change_records",
            "relation_schemas",
        ):
            if hasattr(self.store, field_name):
                setattr(validation_store, field_name, deepcopy(getattr(self.store, field_name)))

        for field_name in (
            "ontology_entities",
            "ontology_assertions",
            "evidence_sources",
            "concept_aliases",
            "guideline_documents",
            "mentions",
            "normalization_decisions",
            "condition_sets",
            "evidence_links",
            "change_records",
        ):
            getattr(validation_store, field_name).update(deepcopy(staged_snapshot.get(field_name, {}) or {}))

        for assertion in staged_snapshot.get("ontology_assertions", {}).values():
            assertion_id = assertion.get("assertion_id")
            if assertion_id and assertion_id in validation_store.ontology_assertions:
                validation_store.ontology_assertions[assertion_id]["status"] = "published"
        for evidence in staged_snapshot.get("evidence_sources", {}).values():
            evidence_id = evidence.get("evidence_id")
            if evidence_id and evidence_id in validation_store.evidence_sources:
                validation_store.evidence_sources[evidence_id]["status"] = "published"
        for alias in staged_snapshot.get("concept_aliases", {}).values():
            alias_id = alias.get("alias_id")
            if alias_id and alias_id in validation_store.concept_aliases:
                validation_store.concept_aliases[alias_id]["status"] = "published"
        for document in staged_snapshot.get("guideline_documents", {}).values():
            document_id = document.get("document_id")
            if document_id and document_id in validation_store.guideline_documents:
                validation_store.guideline_documents[document_id]["status"] = "published"
        return validation_store

    def _validate_staged_snapshot_for_publish(self, staged_snapshot: dict) -> None:
        report = OntologyBaseValidator(self._build_staged_validation_store(staged_snapshot)).validate()
        blocking_codes = {
            "unknown_relation_definition",
            "domain_mismatch",
            "range_mismatch",
            "missing_subject_concept",
            "missing_object_concept",
            "missing_object",
            "missing_condition_set",
            "missing_assertion_evidence",
            "missing_assertion_document",
        }
        blocking_issues = [issue for issue in report.issues if issue.object_type == "assertion" and issue.code in blocking_codes]
        if blocking_issues:
            raise APIError(
                status_code=409,
                code="ontology_publish_validation_failed",
                message="Import job staged ontology snapshot failed validation",
                details=[
                    {
                        "field": f"{issue.object_type}:{issue.object_id}" if issue.object_id else issue.object_type,
                        "message": f"{issue.code}: {issue.message}",
                    }
                    for issue in blocking_issues
                ],
            )

    def _publishable_staged_snapshot(self, staged_snapshot: dict) -> dict:
        publishable = deepcopy(staged_snapshot)
        publishable["ontology_assertions"] = {
            assertion_id: assertion
            for assertion_id, assertion in (publishable.get("ontology_assertions") or {}).items()
            if str(assertion.get("review_status") or "pending") != "rejected"
        }
        return publishable

    def _validate_import_job_publish_gates(self, job: dict[str, object]) -> None:
        validation_report = job.get("validation_report") or {}
        warnings = validation_report.get("warnings") or []
        unresolved_owl_warnings = [
            warning
            for warning in warnings
            if isinstance(warning, str) and warning.startswith("Unresolved OWL ")
        ]
        if unresolved_owl_warnings:
            raise APIError(
                status_code=409,
                code="ontology_publish_validation_failed",
                message="Import job staged ontology snapshot failed validation",
                details=[
                    {
                        "field": "owl_mapping",
                        "message": warning,
                    }
                    for warning in unresolved_owl_warnings
                ],
            )

    def _build_knowledge_card_from_assertions(self, entity_id: str, entity: dict[str, object]) -> dict[str, object]:
        kb_version = str(entity.get("kb_version", ""))
        effects: list[str] = []
        diseases: list[str] = []
        symptoms: list[str] = []
        patterns: list[str] = []
        treatment_methods: list[str] = []
        usage_methods: list[str] = []
        not_for_populations: list[str] = []
        allowed_contexts: list[str] = []
        prohibited_contexts: list[str] = []
        contraindications: list[dict[str, object]] = []
        assertion_count = 0
        evidence_ids: set[str] = set()

        for assertion in self.store.ontology_assertions.values():
            if assertion.get("subject_entity_id") != entity_id:
                continue
            if assertion.get("kb_version") != kb_version:
                continue
            if assertion.get("status") != "published":
                continue
            assertion_count += 1
            evidence_ids.update(str(item) for item in (assertion.get("evidence_ids") or []))
            predicate = assertion.get("predicate_type")
            object_value = str(assertion.get("object_value") or "")
            object_entity_id = assertion.get("object_entity_id")

            if predicate == "HAS_EFFECT" and object_value:
                effects.append(object_value)
            elif predicate == "INDICATED_FOR_DISEASE" and object_value:
                diseases.append(object_value)
            elif predicate == "INDICATED_FOR_SYMPTOM" and object_value:
                symptoms.append(object_value)
            elif predicate == "INDICATED_FOR_PATTERN" and object_value:
                patterns.append(object_value)
            elif predicate == "USES_METHOD" and object_value:
                treatment_methods.append(object_value)
            elif predicate == "HAS_USAGE_METHOD" and object_value:
                usage_methods.append(object_value)
            elif predicate == "NOT_FOR_POPULATION" and object_value:
                not_for_populations.append(object_value)
            elif predicate == "ALLOWED_IN_CONTEXT" and object_value:
                allowed_contexts.append(object_value)
            elif predicate == "PROHIBITED_IN_CONTEXT" and object_value:
                prohibited_contexts.append(object_value)
            elif predicate == "CONTRAINDICATED_WITH":
                contraindications.append(
                    {
                        "target_entity_id": object_entity_id,
                        "target_name": object_value,
                        "relation": "CONTRAINDICATED_WITH",
                    }
                )

        return {
            "entity": {
                "entity_id": entity["entity_id"],
                "standard_name": entity["standard_name"],
                "label": entity["label"],
                "risk_level": entity.get("attributes", {}).get("risk_level", "low"),
            },
            "aliases": entity.get("aliases", []),
            "effects": sorted(set(effects)),
            "diseases": sorted(set(diseases)),
            "symptoms": sorted(set(symptoms)),
            "patterns": sorted(set(patterns)),
            "treatment_methods": sorted(set(treatment_methods)),
            "usage_methods": sorted(set(usage_methods)),
            "not_for_populations": sorted(set(not_for_populations)),
            "allowed_contexts": sorted(set(allowed_contexts)),
            "prohibited_contexts": sorted(set(prohibited_contexts)),
            "contraindications": contraindications,
            "kb_version": kb_version,
            "assertion_count": assertion_count,
            "evidence_count": len(evidence_ids),
            "derived_from_assertions": assertion_count > 0,
            "projection_type": "knowledge_card",
            "projection_version": "projection-v1",
        }

    def _get_or_build_knowledge_card_projection(self, entity_id: str, entity: dict[str, object]) -> dict[str, object]:
        projection = self.store.knowledge_card_projections.get(entity_id)
        if projection is not None:
            return projection
        projection = self._build_knowledge_card_from_assertions(entity_id, entity)
        projection = {
            **projection,
            "projection_type": "knowledge_card",
            "projection_version": projection.get("projection_version", "projection-v1"),
        }
        self._persist_knowledge_card_projection(entity_id, projection)
        return projection

    def _persist_knowledge_card_projection(self, entity_id: str, projection: dict[str, object]) -> None:
        self.store.knowledge_card_projections[entity_id] = projection
        if hasattr(self.store, "persist_knowledge_card_projection"):
            self.store.persist_knowledge_card_projection(entity_id, projection)

    def _rebuild_knowledge_card_projections(self, entity_ids: list[str] | set[str]) -> dict[str, dict[str, object]]:
        rebuilt: dict[str, dict[str, object]] = {}
        for entity_id in sorted(set(str(item) for item in entity_ids)):
            entity = self.store.ontology_entities.get(entity_id)
            if entity is None:
                continue
            projection = {
                **self._build_knowledge_card_from_assertions(entity_id, entity),
                "projection_type": "knowledge_card",
                "projection_version": "projection-v1",
            }
            self._persist_knowledge_card_projection(entity_id, projection)
            rebuilt[entity_id] = projection
        return rebuilt

    def _sync_legacy_knowledge_cards_from_projections(self, entity_ids: list[str] | set[str]) -> None:
        for entity_id in sorted(set(str(item) for item in entity_ids)):
            projection = self.store.knowledge_card_projections.get(entity_id)
            if projection is None:
                self.store.knowledge_cards.pop(entity_id, None)
                continue
            # Keep a compatibility mirror for legacy consumers while projection
            # remains the authoritative runtime read-model.
            self.store.knowledge_cards[entity_id] = deepcopy(projection)

    def build_knowledge_card_detail(self, entity_id: str) -> KnowledgeCardDetail:
        if entity_id not in self.store.ontology_entities:
            raise APIError(status_code=404, code="not_found", message="Ontology entity not found")
        entity = self.store.ontology_entities[entity_id]
        base_card = self._get_or_build_knowledge_card_projection(entity_id, entity)
        assertions = [
            OntologyAssertionView(**assertion)
            for assertion in self.store.ontology_assertions.values()
            if assertion.get("subject_entity_id") == entity_id and assertion.get("status") == "published"
        ]
        evidence_id_set = {
            evidence_id
            for assertion in assertions
            for evidence_id in assertion.evidence_ids
        }
        evidence_sources = [
            EvidenceSourceView(**evidence)
            for evidence_id, evidence in self.store.evidence_sources.items()
            if evidence_id in evidence_id_set and evidence.get("status") == "published"
        ]
        document_id_set = {
            document_id
            for assertion in assertions
            for document_id in [assertion.document_id]
            if document_id
        } | {
            evidence.document_id
            for evidence in evidence_sources
            if evidence.document_id
        }
        guideline_documents = [
            GuidelineDocumentView(**document)
            for document_id, document in self.store.guideline_documents.items()
            if document_id in document_id_set and document.get("status") == "published"
        ]
        return KnowledgeCardDetail(
            **base_card,
            concept_id=entity_id,
            assertions=assertions,
            evidence_sources=evidence_sources,
            guideline_documents=guideline_documents,
        )

    def build_concept_detail(self, entity_id: str) -> OntologyConceptDetail:
        entity = self.store.ontology_entities.get(entity_id)
        if entity is None:
            raise APIError(status_code=404, code="not_found", message="Ontology entity not found")

        assertions = [
            OntologyAssertionView(**assertion)
            for assertion in self.store.ontology_assertions.values()
            if (
                assertion.get("status") == "published"
                and (
                    assertion.get("subject_entity_id") == entity_id
                    or assertion.get("object_entity_id") == entity_id
                )
            )
        ]
        evidence_id_set = {
            evidence_id
            for assertion in assertions
            for evidence_id in assertion.evidence_ids
        }
        evidence_sources = [
            EvidenceSourceView(**evidence)
            for evidence_id, evidence in self.store.evidence_sources.items()
            if evidence_id in evidence_id_set and evidence.get("status") == "published"
        ]
        document_id_set = {
            document_id
            for assertion in assertions
            for document_id in [assertion.document_id]
            if document_id
        } | {
            evidence.document_id
            for evidence in evidence_sources
            if evidence.document_id
        }
        guideline_documents = [
            GuidelineDocumentView(**document)
            for document_id, document in self.store.guideline_documents.items()
            if document_id in document_id_set and document.get("status") == "published"
        ]

        related_ids: dict[str, set[str]] = {
            "Disease": set(),
            "Symptom": set(),
            "Pattern": set(),
            "TreatmentPrinciple": set(),
            "TreatmentMethod": set(),
            "Formula": set(),
            "Herb": set(),
            "UsageMethod": set(),
        }
        for assertion in assertions:
            for candidate_id in [assertion.subject_entity_id, assertion.object_entity_id]:
                if not candidate_id or candidate_id == entity_id:
                    continue
                related = self.store.ontology_entities.get(candidate_id)
                if related is None:
                    continue
                related_ids.setdefault(str(related.get("label")), set()).add(candidate_id)

        def _views(label: str) -> list[OntologyEntityView]:
            return [
                OntologyEntityView(**self.store.ontology_entities[item_id])
                for item_id in sorted(related_ids.get(label, set()))
                if item_id in self.store.ontology_entities
            ]

        return OntologyConceptDetail(
            concept=OntologyEntityView(**entity),
            assertions=assertions,
            evidence_sources=evidence_sources,
            guideline_documents=guideline_documents,
            related_diseases=_views("Disease"),
            related_symptoms=_views("Symptom"),
            related_patterns=_views("Pattern"),
            related_principles=_views("TreatmentPrinciple"),
            related_methods=_views("TreatmentMethod"),
            related_formulas=_views("Formula"),
            related_herbs=_views("Herb"),
            related_usage_methods=_views("UsageMethod"),
        )

    def create_import_job(self, payload: OntologyImportCreateRequest) -> OntologyImportJobView:
        now = utcnow()
        kb_version_id = uuid4()
        import_job_id = uuid4()
        version = {
            "kb_version_id": kb_version_id,
            "version_code": payload.target_version_code,
            "status": "draft",
            "source_type": payload.source_type,
            "source_checksum": None,
            "validation_report": {"warnings": 0, "errors": 0},
            "snapshot_uri": None,
            "published_by": None,
            "published_at": None,
            "rollback_from_version_id": None,
            "created_at": now,
            "updated_at": now,
        }
        job = {
            "import_job_id": import_job_id,
            "kb_version_id": kb_version_id,
            "status": "created",
            "source_uri": payload.source_uri,
            "source_type": payload.source_type,
            "warning_count": 0,
            "error_count": 0,
            "validation_report": {"message": "Ready for validation and publish."},
            "created_at": now,
            "finished_at": None,
        }
        with self.store.lock():
            self.store.kb_versions[kb_version_id] = version
            self.store.import_jobs[import_job_id] = job
        try:
            self.store.persist_kb_version(version)
        except Exception as exc:
            if exc.__class__.__name__ == "UniqueViolation":
                raise APIError(
                    status_code=409,
                    code="kb_version_conflict",
                    message=f"target_version_code already exists: {payload.target_version_code}",
                ) from exc
            raise
        self.store.persist_import_job(job)
        return OntologyImportJobView(**job)

    def import_guideline(self, payload: OntologyImportCreateRequest) -> dict:
        guide_text = (payload.guide_text or "").strip()
        source_uri = (payload.source_uri or payload.guide_file_name or payload.target_version_code).strip()
        guide_title = (payload.guide_title or payload.guide_file_name or source_uri or payload.target_version_code).strip()
        decode_warnings: list[str] = []

        if not guide_text and payload.guide_file_base64:
            if not payload.guide_file_name:
                raise APIError(
                    status_code=400,
                    code="invalid_request",
                    message="guide_file_name is required when guide_file_base64 is provided",
                )
            try:
                guide_text, decode_warnings = self.guideline_extractor.decode_guide_file(
                    payload.guide_file_name,
                    payload.guide_file_base64,
                )
            except ValueError as exc:
                raise APIError(status_code=400, code="invalid_request", message=str(exc)) from exc
            guide_text = guide_text.strip()

        if not guide_text:
            raise APIError(
                status_code=400,
                code="invalid_request",
                message="guide_text or guide_file_base64 is required",
            )

        source_type_normalized = (payload.source_type or "").lower().strip()
        if source_type_normalized in OWL_SOURCE_TYPES:
            return self._import_owl(
                guide_text=guide_text,
                guide_title=guide_title,
                source_uri=source_uri,
                source_type=source_type_normalized,
                target_version_code=payload.target_version_code,
            )

        job_payload = payload.model_copy(update={"source_uri": source_uri})
        job_view = self.create_import_job(job_payload)
        kb_version = self.store.kb_versions[job_view.kb_version_id]
        extracted, llm_warnings = self._extract_guideline_bundle(
            guide_title=guide_title,
            guide_text=guide_text,
            kb_version=kb_version["version_code"],
        )
        combined_warnings = [*decode_warnings, *llm_warnings, *extracted.warnings]
        if not extracted.ontology_entities:
            job = self.store.import_jobs[job_view.import_job_id]
            job["status"] = "failed"
            job["warning_count"] = len(combined_warnings)
            job["error_count"] = 1
            job["validation_report"] = {
                "message": "No ontology content extracted from guideline.",
                "warnings": combined_warnings,
                "ai_telemetry": self._build_ai_telemetry(extracted, phase="failed"),
            }
            job["finished_at"] = utcnow()
            self.store.persist_import_job(job)
            raise APIError(
                status_code=422,
                code="ontology_import_invalid",
                message="No ontology content extracted from guideline",
            )

        now = utcnow()
        ai_telemetry = self._build_ai_telemetry(extracted, phase="extracted")
        vector_index_summary = None
        with self.store.lock():
            self._stage_bundle_on_job(self.store.import_jobs[job_view.import_job_id], extracted)
            kb_version["validation_report"] = {
                "warnings": len(combined_warnings),
                "errors": 0,
                "guide_title": guide_title,
                "entity_count": len(extracted.ontology_entities),
                "knowledge_card_count": len(extracted.knowledge_cards),
                "assertion_count": len(getattr(extracted, "ontology_assertions", {}) or {}),
                "evidence_count": len(getattr(extracted, "evidence_sources", {}) or {}),
                "alias_count": len(getattr(extracted, "concept_aliases", {}) or {}),
                "materials": extracted.extracted_materials,
                "relationship_count": extracted.relationship_count,
                "extractor_engine": extracted.extractor_engine,
                "extractor_model": extracted.extractor_model,
                "extractor_prompt_version": extracted.extractor_prompt_version,
                "fallback_used": extracted.fallback_used,
                "fallback_reason": extracted.fallback_reason,
                "extraction_stats": extracted.extraction_stats,
                "ai_telemetry": ai_telemetry,
                "vector_index": vector_index_summary,
            }
            kb_version["updated_at"] = now
            job = self.store.import_jobs[job_view.import_job_id]
            job["status"] = "extracted"
            job["warning_count"] = len(combined_warnings)
            job["error_count"] = 0
            job["validation_report"] = {
                "message": "Guideline extracted successfully.",
                "warnings": combined_warnings,
                "materials": extracted.extracted_materials,
                "entity_count": len(extracted.ontology_entities),
                "knowledge_card_count": len(extracted.knowledge_cards),
                "assertion_count": len(getattr(extracted, "ontology_assertions", {}) or {}),
                "evidence_count": len(getattr(extracted, "evidence_sources", {}) or {}),
                "alias_count": len(getattr(extracted, "concept_aliases", {}) or {}),
                "relationship_count": extracted.relationship_count,
                "source_type": payload.source_type,
                "extractor_engine": extracted.extractor_engine,
                "extractor_model": extracted.extractor_model,
                "extractor_prompt_version": extracted.extractor_prompt_version,
                "fallback_used": extracted.fallback_used,
                "fallback_reason": extracted.fallback_reason,
                "extraction_stats": extracted.extraction_stats,
                "ai_telemetry": ai_telemetry,
                "vector_index": vector_index_summary,
            }
            job["finished_at"] = now
        self.store.persist_kb_version(kb_version)
        self.store.persist_import_job(job)

        vector_index_summary = None
        if self.vector_search_service is not None:
            try:
                vector_index_summary = self.vector_search_service.index_knowledge_assets(
                    guide_title=guide_title,
                    guide_text=guide_text,
                    kb_version=kb_version["version_code"],
                    knowledge_cards=extracted.knowledge_cards,
                )
            except Exception as exc:
                vector_index_summary = {"indexed_count": 0, "error": str(exc)}

        return {
            "import_job": OntologyImportJobView(**job),
            "kb_version": {
                "kb_version_id": kb_version["kb_version_id"],
                "version_code": kb_version["version_code"],
                "status": kb_version["status"],
            },
            "summary": {
                "guide_title": guide_title,
                "materials": extracted.extracted_materials,
                "entity_count": len(extracted.ontology_entities),
                "knowledge_card_count": len(extracted.knowledge_cards),
                "assertion_count": len(getattr(extracted, "ontology_assertions", {}) or {}),
                "evidence_count": len(getattr(extracted, "evidence_sources", {}) or {}),
                "alias_count": len(getattr(extracted, "concept_aliases", {}) or {}),
                "relationship_count": extracted.relationship_count,
                "warnings": combined_warnings,
                "source_uri": source_uri,
                "extractor_engine": extracted.extractor_engine,
                "extractor_model": extracted.extractor_model,
                "extractor_prompt_version": extracted.extractor_prompt_version,
                "fallback_used": extracted.fallback_used,
                "fallback_reason": extracted.fallback_reason,
                "extraction_stats": extracted.extraction_stats,
                "ai_telemetry": ai_telemetry,
                "vector_index": vector_index_summary,
            },
        }

    def _import_owl(
        self,
        guide_text: str,
        guide_title: str,
        source_uri: str,
        source_type: str,
        target_version_code: str,
    ) -> dict:
        importer = OwlOntologyImporter()
        result = importer.parse_owl_content(
            content=guide_text.encode("utf-8"),
            source_type=source_type,
            file_name=source_uri,
        )

        if not result.classes:
            job_payload = OntologyImportCreateRequest(
                source_uri=source_uri,
                source_type=source_type,
                target_version_code=target_version_code,
            )
            job_view = self.create_import_job(job_payload)
            job = self.store.import_jobs[job_view.import_job_id]
            job["status"] = "failed"
            job["error_count"] = 1
            job["validation_report"] = {
                "message": "No OWL classes found in ontology file.",
                "warnings": result.warnings,
                "ai_telemetry": {
                    "phase": "failed",
                    "extractor_engine": "owl_import",
                    "warning_count": len(result.warnings),
                },
            }
            job["finished_at"] = utcnow()
            self.store.persist_import_job(job)
            raise APIError(
                status_code=422,
                code="ontology_import_invalid",
                message="No OWL classes found in ontology file",
            )

        kb_version_code = target_version_code or f"kb-owl-{utcnow().strftime('%Y%m%d-%H%M%S')}"
        bundle = importer.to_ontology_bundle(
            result=result,
            kb_version=kb_version_code,
            guide_title=guide_title,
        )

        if not bundle.ontology_entities:
            job_payload = OntologyImportCreateRequest(
                source_uri=source_uri,
                source_type=source_type,
                target_version_code=kb_version_code,
            )
            job_view = self.create_import_job(job_payload)
            job = self.store.import_jobs[job_view.import_job_id]
            job["status"] = "failed"
            job["error_count"] = 1
            job["validation_report"] = {
                "message": "No ontology content extracted from OWL file.",
                "warnings": bundle.warnings,
                "ai_telemetry": {
                    "phase": "failed",
                    "extractor_engine": bundle.extractor_engine,
                    "warning_count": len(bundle.warnings),
                },
            }
            job["finished_at"] = utcnow()
            self.store.persist_import_job(job)
            raise APIError(
                status_code=422,
                code="ontology_import_invalid",
                message="No ontology content extracted from OWL file",
            )

        job_payload = OntologyImportCreateRequest(
            source_uri=source_uri,
            source_type=source_type,
            target_version_code=kb_version_code,
        )
        job_view = self.create_import_job(job_payload)
        kb_version = self.store.kb_versions[job_view.kb_version_id]

        now = utcnow()
        vector_index_summary = None
        ai_telemetry = {
            "phase": "extracted",
            "extractor_engine": bundle.extractor_engine,
            "extractor_model": bundle.extractor_model,
            "extractor_prompt_version": bundle.extractor_prompt_version,
            "fallback_used": False,
            "warning_count": len(bundle.warnings),
            "entity_count": len(bundle.ontology_entities),
            "knowledge_card_count": len(bundle.knowledge_cards),
            "assertion_count": len(getattr(bundle, "ontology_assertions", {}) or {}),
            "evidence_count": len(getattr(bundle, "evidence_sources", {}) or {}),
            "alias_count": len(getattr(bundle, "concept_aliases", {}) or {}),
            "relationship_count": bundle.relationship_count,
        }
        with self.store.lock():
            self._stage_bundle_on_job(self.store.import_jobs[job_view.import_job_id], bundle)
            kb_version["validation_report"] = {
                "warnings": len(bundle.warnings),
                "errors": 0,
                "guide_title": guide_title,
                "entity_count": len(bundle.ontology_entities),
                "knowledge_card_count": len(bundle.knowledge_cards),
                "assertion_count": len(getattr(bundle, "ontology_assertions", {}) or {}),
                "evidence_count": len(getattr(bundle, "evidence_sources", {}) or {}),
                "alias_count": len(getattr(bundle, "concept_aliases", {}) or {}),
                "materials": bundle.extracted_materials,
                "relationship_count": bundle.relationship_count,
                "extractor_engine": bundle.extractor_engine,
                "extractor_model": bundle.extractor_model,
                "extractor_prompt_version": bundle.extractor_prompt_version,
                "fallback_used": False,
                "fallback_reason": None,
                "extraction_stats": bundle.extraction_stats,
                "ai_telemetry": ai_telemetry,
                "vector_index": vector_index_summary,
            }
            kb_version["updated_at"] = now
            job = self.store.import_jobs[job_view.import_job_id]
            job["status"] = "extracted"
            job["warning_count"] = len(bundle.warnings)
            job["error_count"] = 0
            job["validation_report"] = {
                "message": f"OWL ontology imported: {len(bundle.ontology_entities)} entities, "
                f"{len(bundle.knowledge_cards)} knowledge cards.",
                "warnings": bundle.warnings,
                "materials": bundle.extracted_materials,
                "entity_count": len(bundle.ontology_entities),
                "knowledge_card_count": len(bundle.knowledge_cards),
                "assertion_count": len(getattr(bundle, "ontology_assertions", {}) or {}),
                "evidence_count": len(getattr(bundle, "evidence_sources", {}) or {}),
                "alias_count": len(getattr(bundle, "concept_aliases", {}) or {}),
                "relationship_count": bundle.relationship_count,
                "source_type": source_type,
                "extractor_engine": bundle.extractor_engine,
                "extractor_model": bundle.extractor_model,
                "extractor_prompt_version": bundle.extractor_prompt_version,
                "fallback_used": False,
                "fallback_reason": None,
                "extraction_stats": bundle.extraction_stats,
                "ai_telemetry": ai_telemetry,
                "vector_index": vector_index_summary,
            }
            job["finished_at"] = now
        self.store.persist_kb_version(kb_version)
        self.store.persist_import_job(job)

        if self.vector_search_service is not None:
            try:
                vector_index_summary = self.vector_search_service.index_knowledge_assets(
                    guide_title=guide_title,
                    guide_text=guide_text,
                    kb_version=kb_version["version_code"],
                    knowledge_cards=bundle.knowledge_cards,
                )
            except Exception as exc:
                vector_index_summary = {"indexed_count": 0, "error": str(exc)}

        return {
            "import_job": OntologyImportJobView(**job),
            "kb_version": {
                "kb_version_id": kb_version["kb_version_id"],
                "version_code": kb_version["version_code"],
                "status": kb_version["status"],
            },
            "summary": {
                "guide_title": guide_title,
                "materials": bundle.extracted_materials,
                "entity_count": len(bundle.ontology_entities),
                "knowledge_card_count": len(bundle.knowledge_cards),
                "assertion_count": len(getattr(bundle, "ontology_assertions", {}) or {}),
                "evidence_count": len(getattr(bundle, "evidence_sources", {}) or {}),
                "alias_count": len(getattr(bundle, "concept_aliases", {}) or {}),
                "relationship_count": bundle.relationship_count,
                "warnings": bundle.warnings,
                "source_uri": source_uri,
                "extractor_engine": bundle.extractor_engine,
                "extractor_model": bundle.extractor_model,
                "extractor_prompt_version": bundle.extractor_prompt_version,
                "fallback_used": False,
                "fallback_reason": None,
                "extraction_stats": bundle.extraction_stats,
                "ai_telemetry": ai_telemetry,
                "vector_index": vector_index_summary,
            },
        }

    def _extract_guideline_bundle(
        self,
        guide_title: str,
        guide_text: str,
        kb_version: str,
    ) -> tuple[object, list[str]]:
        llm_warnings: list[str] = []
        if self.guideline_llm_extractor.is_enabled():
            try:
                extracted = self.guideline_llm_extractor.extract(
                    guide_title=guide_title,
                    guide_text=guide_text,
                    kb_version=kb_version,
                )
                if extracted.ontology_entities:
                    extracted.ontology_assertions, validation_warnings = self.guideline_extractor._validate_assertions(
                        extracted.ontology_entities,
                        extracted.ontology_assertions,
                        relation_schemas=getattr(self.store, "relation_schemas", None),
                    )
                    extracted.warnings.extend(validation_warnings)
                    return extracted, llm_warnings
                llm_warnings.append("大模型未提取到有效实体，已自动回退到规则抽取。")
            except Exception as exc:
                llm_warnings.append(f"大模型抽取失败，已自动回退规则抽取：{exc}")

        extracted = self.guideline_extractor.extract(
            guide_title=guide_title,
            guide_text=guide_text,
            kb_version=kb_version,
        )
        extracted.ontology_assertions, validation_warnings = self.guideline_extractor._validate_assertions(
            extracted.ontology_entities,
            extracted.ontology_assertions,
            relation_schemas=getattr(self.store, "relation_schemas", None),
        )
        extracted.warnings.extend(validation_warnings)
        if llm_warnings:
            extracted.fallback_used = True
            extracted.fallback_reason = llm_warnings[-1]
            extracted.extractor_engine = "rule_fallback"
            extracted.extraction_stats["fallback_trigger_count"] = len(llm_warnings)
        return extracted, llm_warnings

    def _build_ai_telemetry(self, bundle: object, *, phase: str) -> dict:
        extraction_stats = getattr(bundle, "extraction_stats", {}) or {}
        return {
            "phase": phase,
            "extractor_engine": getattr(bundle, "extractor_engine", None),
            "extractor_model": getattr(bundle, "extractor_model", None),
            "extractor_prompt_version": getattr(bundle, "extractor_prompt_version", None),
            "fallback_used": getattr(bundle, "fallback_used", False),
            "fallback_reason": getattr(bundle, "fallback_reason", None),
            "warning_count": len(getattr(bundle, "warnings", []) or []),
            "entity_count": len(getattr(bundle, "ontology_entities", {}) or {}),
            "knowledge_card_count": len(getattr(bundle, "knowledge_cards", {}) or {}),
            "relationship_count": getattr(bundle, "relationship_count", 0),
            "extraction_stats": extraction_stats,
        }

    def get_import_job(self, import_job_id: UUID) -> OntologyImportJobView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        return OntologyImportJobView(**job)

    def _build_evidence_context(self, staged_snapshot: dict, evidence_ids: list[str]) -> list[dict[str, object]]:
        staged_evidence = staged_snapshot.get("evidence_sources", {}) or {}
        evidence_context: list[dict[str, object]] = []
        for evidence_id in evidence_ids:
            evidence = staged_evidence.get(str(evidence_id))
            if evidence is None:
                continue
            evidence_context.append(
                {
                    "evidence_id": str(evidence.get("evidence_id") or evidence_id),
                    "source_title": evidence.get("source_title"),
                    "source_text": evidence.get("source_text") or evidence.get("quoted_text") or "",
                    "source_uri": evidence.get("source_uri"),
                }
            )
        return evidence_context

    def _build_concept_proposal_view(self, proposal: dict, staged_snapshot: dict) -> ConceptProposalView:
        mention_id = str(proposal.get("mention_id") or "")
        mention = (staged_snapshot.get("mentions", {}) or {}).get(mention_id) or {}
        evidence_ids = [str(item) for item in proposal.get("evidence_ids") or []]
        return ConceptProposalView(
            proposal_id=str(proposal.get("proposal_id") or ""),
            decision_id=str(proposal.get("decision_id") or ""),
            mention_id=mention_id,
            surface_text=str(proposal.get("surface_text") or mention.get("surface_text") or ""),
            concept_type=str(proposal.get("concept_type") or ""),
            standard_name=str(proposal.get("standard_name") or ""),
            definition=str(proposal.get("definition") or ""),
            evidence_ids=evidence_ids,
            evidence_sources=self._build_evidence_context(staged_snapshot, evidence_ids),
            source_note=proposal.get("source_note"),
            status=str(proposal.get("status") or ""),
            proposed_concept_id=proposal.get("proposed_concept_id"),
            created_at=proposal["created_at"],
            reviewed_at=proposal.get("reviewed_at"),
            reviewed_by=proposal.get("reviewed_by"),
            review_reason=proposal.get("review_reason"),
        )

    def _build_staged_assertion_bundle(self, assertion: dict, staged_snapshot: dict) -> AssertionBundleView:
        condition = None
        condition_set_id = assertion.get("condition_set_id")
        if condition_set_id and condition_set_id in (staged_snapshot.get("condition_sets") or {}):
            condition = ConditionSetView(**staged_snapshot["condition_sets"][condition_set_id])
        evidence_ids = [str(item) for item in assertion.get("evidence_ids") or []]
        evidence_sources = [
            EvidenceSourceView(**evidence)
            for evidence_id, evidence in (staged_snapshot.get("evidence_sources") or {}).items()
            if evidence_id in evidence_ids
        ]
        assertion_id = str(assertion.get("assertion_id") or "")
        change_records = [
            ChangeRecordView(**item)
            for item in (staged_snapshot.get("change_records") or {}).values()
            if item.get("object_type") == "assertion" and item.get("object_id") == assertion_id
        ]
        return AssertionBundleView(
            assertion=OntologyAssertionView(**assertion),
            condition=condition,
            evidence_sources=evidence_sources,
            evidence_links=[],
            change_records=change_records,
        )

    def get_import_governance(self, import_job_id: UUID) -> ImportGovernanceView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")

        staged_snapshot = job.get("staged_snapshot") or {}
        issues: list[ImportGovernanceIssueView] = []

        validation_report = job.get("validation_report") or {}
        warnings = validation_report.get("warnings") or []
        if not isinstance(warnings, (list, tuple)):
            warnings = [warnings] if warnings not in (0, "") else []
        for index, warning in enumerate(warnings):
            if isinstance(warning, dict):
                code = str(warning.get("code") or "validation_warning")
                message = str(warning.get("message") or warning.get("detail") or warning)
                severity = str(warning.get("severity") or "warning")
                status = str(warning.get("status") or "open")
                object_type = str(warning.get("object_type") or "import_job")
                object_id = warning.get("object_id")
                title = str(warning.get("title") or "Import validation warning")
                action = str(warning.get("action") or "review_validation_warning")
            else:
                code = "validation_warning"
                message = str(warning)
                severity = "warning"
                status = "open"
                object_type = "import_job"
                object_id = str(import_job_id)
                title = "Import validation warning"
                action = "review_validation_warning"
            issues.append(
                ImportGovernanceIssueView(
                    issue_id=f"validation-warning:{index}",
                    severity=severity,
                    status=status,
                    code=code,
                    title=title,
                    message=message,
                    object_type=object_type,
                    object_id=str(object_id) if object_id is not None else None,
                    action=action,
                )
            )

        staged_mentions = staged_snapshot.get("mentions", {}) or {}
        staged_decisions = staged_snapshot.get("normalization_decisions", {}) or {}
        staged_evidence_ids = sorted(str(item) for item in (staged_snapshot.get("evidence_sources", {}) or {}))
        for decision_id, decision in sorted(staged_decisions.items(), key=lambda item: str(item[0])):
            decision_status = str(decision.get("status") or "")
            if decision_status not in {"unresolved", "ambiguous"}:
                continue
            mention_id = str(decision.get("mention_id") or "")
            mention = staged_mentions.get(mention_id) or {}
            surface_text = str(mention.get("surface_text") or "")
            decision_reason = str(decision.get("decision_reason") or "").strip()
            if decision_reason and surface_text and surface_text not in decision_reason:
                message = f"{surface_text}: {decision_reason}"
            else:
                message = decision_reason or f"Normalization decision for {surface_text or mention_id or decision_id} is {decision_status}"
            decision_evidence_ids = [str(item) for item in decision.get("evidence_ids") or []]
            if not decision_evidence_ids:
                decision_evidence_ids = staged_evidence_ids
            issues.append(
                ImportGovernanceIssueView(
                    issue_id=f"normalization:{decision_id}",
                    severity="warning",
                    status=decision_status,
                    code=f"normalization_{decision_status}",
                    title=f"{decision_status.title()} normalization decision",
                    message=message,
                    object_type="normalization_decision",
                    object_id=str(decision_id),
                    action="resolve_normalization",
                    mention_id=mention_id or None,
                    surface_text=surface_text or None,
                    candidate_list=decision.get("candidate_list") or [],
                    evidence_ids=decision_evidence_ids,
                    evidence_sources=self._build_evidence_context(staged_snapshot, decision_evidence_ids),
                    resolved_concept_id=decision.get("resolved_concept_id"),
                    canonical_name=decision.get("canonical_name"),
                )
            )

        staged_proposals = staged_snapshot.get("concept_proposals", {}) or {}
        concept_proposals = [
            self._build_concept_proposal_view(proposal, staged_snapshot)
            for _, proposal in sorted(staged_proposals.items(), key=lambda item: str(item[0]))
        ]
        staged_assertions = [
            self._build_staged_assertion_bundle(assertion, staged_snapshot)
            for _, assertion in sorted(
                (staged_snapshot.get("ontology_assertions", {}) or {}).items(),
                key=lambda item: str(item[0]),
            )
        ]

        if staged_snapshot:
            validation_store = self._build_staged_validation_store(staged_snapshot)
            staged_ids_by_object_type = {
                "concept": set(staged_snapshot.get("ontology_entities", {}) or {}),
                "assertion": set(staged_snapshot.get("ontology_assertions", {}) or {}),
                "evidence_source": set(staged_snapshot.get("evidence_sources", {}) or {}),
                "concept_alias": set(staged_snapshot.get("concept_aliases", {}) or {}),
                "guideline_document": set(staged_snapshot.get("guideline_documents", {}) or {}),
                "mention": set(staged_snapshot.get("mentions", {}) or {}),
                "normalization_decision": set(staged_decisions),
                "condition_set": set(staged_snapshot.get("condition_sets", {}) or {}),
            }
            validation_result = OntologyBaseValidator(validation_store).validate()
            for index, validation_issue in enumerate(validation_result.issues):
                object_type = validation_issue.object_type
                object_id = validation_issue.object_id
                if object_id is None or object_id not in staged_ids_by_object_type.get(object_type, set()):
                    continue
                issues.append(
                    ImportGovernanceIssueView(
                        issue_id=f"staged-validator:{index}:{object_type}:{object_id}",
                        severity=validation_issue.severity,
                        status="open",
                        code=validation_issue.code,
                        title=f"Staged validation: {validation_issue.code}",
                        message=validation_issue.message,
                        object_type=object_type,
                        object_id=object_id,
                        action="fix_validation_issue",
                    )
                )

        summary_counts = {
            "concepts": len(staged_snapshot.get("ontology_entities", {}) or {}),
            "assertions": len(staged_snapshot.get("ontology_assertions", {}) or {}),
            "evidence": len(staged_snapshot.get("evidence_sources", {}) or {}),
            "mentions": len(staged_mentions),
            "normalizations": len(staged_decisions),
        }
        severity_counts = dict(sorted(Counter(issue.severity for issue in issues).items()))
        status_counts = dict(sorted(Counter(issue.status for issue in issues).items()))
        kb_version = self.store.kb_versions.get(job.get("kb_version_id"), {})
        return ImportGovernanceView(
            import_job=OntologyImportJobView(**job),
            release_code=str(kb_version.get("version_code") or ""),
            summary=ImportGovernanceSummaryView(
                **summary_counts,
                issue_count=len(issues),
                issue_counts_by_severity=severity_counts,
                issue_counts_by_status=status_counts,
            ),
            issues=issues,
            staged_assertions=staged_assertions,
            concept_proposals=concept_proposals,
        )

    def publish_import_job(self, import_job_id: UUID) -> OntologyImportJobView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        staged_snapshot = job.get("staged_snapshot") or {}
        if not staged_snapshot:
            raise APIError(status_code=409, code="invalid_state", message="Import job has no staged ontology snapshot")
        self._validate_import_job_publish_gates(job)
        publish_snapshot = self._publishable_staged_snapshot(staged_snapshot)
        self._validate_staged_snapshot_for_publish(publish_snapshot)
        now = utcnow()
        with self.store.lock():
            job["status"] = "published"
            job["finished_at"] = now
            kb_version = self.store.kb_versions[job["kb_version_id"]]
            kb_version["status"] = "published"
            kb_version["published_at"] = now
            kb_version["snapshot_uri"] = f"memory://{kb_version['version_code']}"
            kb_version["updated_at"] = now
            for assertion in publish_snapshot.get("ontology_assertions", {}).values():
                assertion["status"] = "published"
            for evidence in publish_snapshot.get("evidence_sources", {}).values():
                evidence["status"] = "published"
            for alias in publish_snapshot.get("concept_aliases", {}).values():
                alias["status"] = "published"
            for document in publish_snapshot.get("guideline_documents", {}).values():
                document["status"] = "published"
            self.store.ontology_entities.update(publish_snapshot.get("ontology_entities", {}))
            self.store.ontology_assertions.update(publish_snapshot.get("ontology_assertions", {}))
            self.store.evidence_sources.update(publish_snapshot.get("evidence_sources", {}))
            self.store.concept_aliases.update(publish_snapshot.get("concept_aliases", {}))
            self.store.guideline_documents.update(publish_snapshot.get("guideline_documents", {}))
            self.store.mentions.update(publish_snapshot.get("mentions", {}))
            self.store.normalization_decisions.update(publish_snapshot.get("normalization_decisions", {}))
            self.store.condition_sets.update(publish_snapshot.get("condition_sets", {}))
            self.store.change_records.update(publish_snapshot.get("change_records", {}))
            changed_entity_ids = set(publish_snapshot.get("ontology_entities", {}).keys())
            self._rebuild_knowledge_card_projections(changed_entity_ids)
            self._sync_legacy_knowledge_cards_from_projections(changed_entity_ids)
        self.store.persist_import_job(job)
        self.store.persist_kb_version(kb_version)
        if hasattr(self.store, "persist_ontology_assets"):
            persist_assets = getattr(self.store, "persist_ontology_assets")
            persist_assets(
                ontology_assertions=publish_snapshot.get("ontology_assertions", {}),
                evidence_sources=publish_snapshot.get("evidence_sources", {}),
                concept_aliases=publish_snapshot.get("concept_aliases", {}),
                guideline_documents=publish_snapshot.get("guideline_documents", {}),
            )
        for mention in publish_snapshot.get("mentions", {}).values():
            self.store.persist_mention(mention)
        for decision in publish_snapshot.get("normalization_decisions", {}).values():
            self.store.persist_normalization_decision(decision)
        if hasattr(self.store, "_replace_neo4j_graph"):
            replace_graph = getattr(self.store, "_replace_neo4j_graph")
            replace_graph(self.store.ontology_entities, self.store.knowledge_card_projections)
        return OntologyImportJobView(**job)

    def get_entity(self, entity_id: str) -> OntologyEntityView:
        entity = self.store.ontology_entities.get(entity_id)
        if entity is None:
            raise APIError(status_code=404, code="not_found", message="Ontology entity not found")
        return OntologyEntityView(**entity)

    def get_disease_detail(self, entity_id: str) -> OntologyConceptDetail:
        detail = self.build_concept_detail(entity_id)
        if detail.concept.label != "Disease":
            raise APIError(status_code=400, code="invalid_request", message="Entity is not a Disease concept")
        return detail

    def get_symptom_detail(self, entity_id: str) -> OntologyConceptDetail:
        detail = self.build_concept_detail(entity_id)
        if detail.concept.label != "Symptom":
            raise APIError(status_code=400, code="invalid_request", message="Entity is not a Symptom concept")
        return detail

    def get_pattern_detail(self, entity_id: str) -> OntologyConceptDetail:
        detail = self.build_concept_detail(entity_id)
        if detail.concept.label != "Pattern":
            raise APIError(status_code=400, code="invalid_request", message="Entity is not a Pattern concept")
        return detail

    def get_formula_detail(self, entity_id: str) -> OntologyConceptDetail:
        detail = self.build_concept_detail(entity_id)
        if detail.concept.label != "Formula":
            raise APIError(status_code=400, code="invalid_request", message="Entity is not a Formula concept")
        return detail

    def get_herb_detail(self, entity_id: str) -> OntologyConceptDetail:
        detail = self.build_concept_detail(entity_id)
        if detail.concept.label != "Herb":
            raise APIError(status_code=400, code="invalid_request", message="Entity is not a Herb concept")
        return detail

    def get_treatment_method_detail(self, entity_id: str) -> OntologyConceptDetail:
        detail = self.build_concept_detail(entity_id)
        if detail.concept.label != "TreatmentMethod":
            raise APIError(status_code=400, code="invalid_request", message="Entity is not a TreatmentMethod concept")
        return detail

    def get_treatment_principle_detail(self, entity_id: str) -> OntologyConceptDetail:
        detail = self.build_concept_detail(entity_id)
        if detail.concept.label != "TreatmentPrinciple":
            raise APIError(status_code=400, code="invalid_request", message="Entity is not a TreatmentPrinciple concept")
        return detail

    def get_knowledge_card(self, entity_id: str) -> KnowledgeCard:
        return self.build_knowledge_card_detail(entity_id)

    def get_projection_detail(self, entity_id: str) -> KnowledgeCardDetail:
        return self.build_knowledge_card_detail(entity_id)

    def get_mention(self, mention_id: str) -> MentionView:
        mention = self.store.mentions.get(mention_id)
        if mention is None:
            raise APIError(status_code=404, code="not_found", message="Mention not found")
        return MentionView(**mention)

    def get_normalization_decision(self, decision_id: str) -> NormalizationDecisionView:
        decision = self.store.normalization_decisions.get(decision_id)
        if decision is None:
            raise APIError(status_code=404, code="not_found", message="Normalization decision not found")
        return NormalizationDecisionView(**decision)

    def list_normalization_decisions(
        self,
        *,
        status: str | None = None,
        kb_version: str | None = None,
        source_type: str | None = None,
    ) -> list[NormalizationDecisionView]:
        items = list(self.store.normalization_decisions.values())
        if status:
            items = [item for item in items if str(item.get("status") or "") == status]
        if kb_version:
            items = [item for item in items if str(item.get("kb_version") or "") == kb_version]
        if source_type:
            mention_ids = {
                mention_id
                for mention_id, mention in self.store.mentions.items()
                if str(mention.get("source_type") or "") == source_type
            }
            items = [item for item in items if str(item.get("mention_id") or "") in mention_ids]
        items.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("decision_id") or "")))
        return [NormalizationDecisionView(**item) for item in items]

    def review_normalization_decision(
        self,
        decision_id: str,
        payload: NormalizationDecisionReviewRequest,
    ) -> NormalizationDecisionView:
        decision = self.store.normalization_decisions.get(decision_id)
        if decision is None:
            raise APIError(status_code=404, code="not_found", message="Normalization decision not found")
        previous_status = str(decision.get("status") or "")
        created_alias_id: str | None = None
        if payload.status == "resolved":
            if not payload.resolved_concept_id:
                raise APIError(
                    status_code=400,
                    code="invalid_request",
                    message="resolved_concept_id is required when resolving a normalization decision",
                )
            concept = self.store.ontology_entities.get(payload.resolved_concept_id)
            if concept is None:
                raise APIError(status_code=404, code="not_found", message="Resolved concept not found")
            decision["resolved_concept_id"] = payload.resolved_concept_id
            decision["canonical_name"] = payload.canonical_name or concept.get("standard_name")
            decision["candidate_list"] = [
                {
                    "concept_id": payload.resolved_concept_id,
                    "canonical_name": decision["canonical_name"],
                    "concept_type": concept.get("label"),
                    "score": 1.0,
                }
            ]
            decision["confidence_score"] = 1.0
            if payload.create_alias:
                created_alias_id = self._create_alias_from_normalization_decision(
                    decision,
                    concept,
                    operator_id=payload.operator_id,
                )
        else:
            decision["resolved_concept_id"] = None
            decision["canonical_name"] = payload.canonical_name
            decision["confidence_score"] = 0.0
        decision["status"] = payload.status
        decision["decision_reason"] = payload.reason

        change_id = f"chg_norm_{uuid4().hex}"
        self.store.change_records[change_id] = {
            "change_id": change_id,
            "object_type": "normalization_decision",
            "object_id": decision_id,
            "change_type": "review",
            "from_version": previous_status,
            "to_version": payload.status,
            "change_summary": f"Normalization decision reviewed: {previous_status} -> {payload.status}",
            "reason": payload.reason,
            "impact_note": f"created_alias_id={created_alias_id}" if created_alias_id else None,
            "created_at": utcnow(),
            "created_by": payload.operator_id,
            "review_status": "approved",
        }
        self.store.persist_normalization_decision(decision)
        return NormalizationDecisionView(**decision)

    def review_staged_normalization_decision(
        self,
        import_job_id: UUID,
        decision_id: str,
        payload: NormalizationDecisionReviewRequest,
    ) -> NormalizationDecisionView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        staged_snapshot = job.get("staged_snapshot") or {}
        if not staged_snapshot:
            raise APIError(status_code=409, code="invalid_state", message="Import job has no staged ontology snapshot")
        staged_decisions = staged_snapshot.get("normalization_decisions") or {}
        decision = staged_decisions.get(decision_id)
        if decision is None:
            raise APIError(status_code=404, code="not_found", message="Normalization decision not found in import job")

        previous_status = str(decision.get("status") or "")
        created_alias_id: str | None = None
        if payload.status == "resolved":
            if not payload.resolved_concept_id:
                raise APIError(
                    status_code=400,
                    code="invalid_request",
                    message="resolved_concept_id is required when resolving a normalization decision",
                )
            concept = self.store.ontology_entities.get(payload.resolved_concept_id)
            if concept is None:
                concept = (staged_snapshot.get("ontology_entities") or {}).get(payload.resolved_concept_id)
            if concept is None:
                raise APIError(status_code=404, code="not_found", message="Resolved concept not found")
            decision["resolved_concept_id"] = payload.resolved_concept_id
            decision["canonical_name"] = payload.canonical_name or concept.get("standard_name")
            decision["candidate_list"] = [
                {
                    "concept_id": payload.resolved_concept_id,
                    "canonical_name": decision["canonical_name"],
                    "concept_type": concept.get("label"),
                    "score": 1.0,
                }
            ]
            decision["confidence_score"] = 1.0
            if payload.create_alias:
                created_alias_id = self._create_staged_alias_from_normalization_decision(
                    staged_snapshot,
                    decision,
                    concept,
                    operator_id=payload.operator_id,
                )
        else:
            decision["resolved_concept_id"] = None
            decision["canonical_name"] = payload.canonical_name
            decision["confidence_score"] = 0.0
        decision["status"] = payload.status
        decision["decision_reason"] = payload.reason

        change_id = f"chg_norm_{uuid4().hex}"
        staged_snapshot.setdefault("change_records", {})[change_id] = {
            "change_id": change_id,
            "object_type": "normalization_decision",
            "object_id": decision_id,
            "change_type": "review",
            "from_version": previous_status,
            "to_version": payload.status,
            "change_summary": f"Normalization decision reviewed: {previous_status} -> {payload.status}",
            "reason": payload.reason,
            "impact_note": f"created_alias_id={created_alias_id}" if created_alias_id else None,
            "created_at": utcnow(),
            "created_by": payload.operator_id,
            "review_status": "approved",
        }
        self.store.persist_import_job(job)
        return NormalizationDecisionView(**decision)

    def review_staged_assertion(
        self,
        import_job_id: UUID,
        assertion_id: str,
        payload: StagedAssertionReviewRequest,
    ) -> AssertionBundleView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        staged_snapshot = job.get("staged_snapshot") or {}
        if not staged_snapshot:
            raise APIError(status_code=409, code="invalid_state", message="Import job has no staged ontology snapshot")
        staged_assertions = staged_snapshot.get("ontology_assertions") or {}
        assertion = staged_assertions.get(assertion_id)
        if assertion is None:
            raise APIError(status_code=404, code="not_found", message="Assertion not found in import job")
        previous_status = str(assertion.get("review_status") or "pending")
        now = utcnow()
        assertion["review_status"] = payload.status
        assertion["review_reason"] = payload.reason
        assertion["reviewed_by"] = payload.operator_id
        assertion["reviewed_at"] = now
        change_id = f"chg_assert_{uuid4().hex}"
        staged_snapshot.setdefault("change_records", {})[change_id] = {
            "change_id": change_id,
            "object_type": "assertion",
            "object_id": assertion_id,
            "change_type": "review",
            "from_version": previous_status,
            "to_version": payload.status,
            "change_summary": f"Assertion reviewed: {previous_status} -> {payload.status}",
            "reason": payload.reason,
            "impact_note": "excluded_from_publish" if payload.status == "rejected" else None,
            "created_at": now,
            "created_by": payload.operator_id,
            "review_status": "approved",
        }
        self.store.persist_import_job(job)
        return self._build_staged_assertion_bundle(assertion, staged_snapshot)

    def create_concept_proposal(
        self,
        import_job_id: UUID,
        decision_id: str,
        payload: ConceptProposalCreateRequest,
    ) -> ConceptProposalView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        staged_snapshot = job.get("staged_snapshot") or {}
        if not staged_snapshot:
            raise APIError(status_code=409, code="invalid_state", message="Import job has no staged ontology snapshot")

        decision = (staged_snapshot.get("normalization_decisions") or {}).get(decision_id)
        if decision is None:
            raise APIError(status_code=404, code="not_found", message="Normalization decision not found in import job")
        if str(decision.get("status") or "") != "unresolved":
            raise APIError(
                status_code=409,
                code="invalid_state",
                message="Concept proposals can only be created for unresolved normalization decisions",
            )
        if any(
            str(proposal.get("decision_id") or "") == decision_id
            and str(proposal.get("status") or "") == "pending_review"
            for proposal in (staged_snapshot.get("concept_proposals") or {}).values()
        ):
            raise APIError(
                status_code=409,
                code="invalid_state",
                message="A pending concept proposal already exists for this normalization decision",
            )

        concept_type = str(payload.concept_type or "").strip()
        if concept_type not in ALLOWED_ONTOLOGY_TYPES:
            raise APIError(
                status_code=400,
                code="invalid_request",
                message=f"concept_type must be one of the allowed ontology types: {concept_type}",
            )

        evidence_ids = [str(item).strip() for item in payload.evidence_ids]
        missing_evidence_ids = sorted(
            {
                evidence_id
                for evidence_id in evidence_ids
                if not evidence_id or evidence_id not in (staged_snapshot.get("evidence_sources") or {})
            }
        )
        if missing_evidence_ids:
            raise APIError(
                status_code=400,
                code="invalid_request",
                message="All evidence_ids must exist in the import job staged evidence sources",
                details=[{"field": "evidence_ids", "message": ", ".join(missing_evidence_ids)}],
            )

        mention_id = str(decision.get("mention_id") or "")
        mention = (staged_snapshot.get("mentions") or {}).get(mention_id)
        if mention is None:
            raise APIError(status_code=404, code="not_found", message="Mention not found in import job")
        surface_text = str(mention.get("surface_text") or "").strip()
        if not surface_text:
            raise APIError(status_code=409, code="invalid_state", message="Normalization mention has no surface text")

        now = utcnow()
        proposal_id = f"proposal_{uuid4().hex}"
        proposal = {
            "proposal_id": proposal_id,
            "decision_id": decision_id,
            "mention_id": mention_id,
            "surface_text": surface_text,
            "concept_type": concept_type,
            "standard_name": str(payload.standard_name).strip(),
            "definition": str(payload.definition).strip(),
            "evidence_ids": evidence_ids,
            "source_note": (payload.source_note or "").strip() or None,
            "status": "pending_review",
            "proposed_concept_id": None,
            "created_at": now,
            "reviewed_at": None,
            "reviewed_by": None,
            "review_reason": None,
            "created_by": payload.operator_id,
            "kb_version": decision.get("kb_version"),
        }
        with self.store.lock():
            staged_snapshot.setdefault("concept_proposals", {})[proposal_id] = proposal
        self.store.persist_import_job(job)
        return self._build_concept_proposal_view(proposal, staged_snapshot)

    def list_concept_proposals(self, import_job_id: UUID) -> list[ConceptProposalView]:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        staged_snapshot = job.get("staged_snapshot") or {}
        if not staged_snapshot:
            raise APIError(status_code=409, code="invalid_state", message="Import job has no staged ontology snapshot")
        proposals = staged_snapshot.get("concept_proposals", {}) or {}
        items = sorted(
            proposals.values(),
            key=lambda item: (str(item.get("created_at") or ""), str(item.get("proposal_id") or "")),
        )
        return [self._build_concept_proposal_view(proposal, staged_snapshot) for proposal in items]

    def review_concept_proposal(
        self,
        import_job_id: UUID,
        proposal_id: str,
        payload: ConceptProposalReviewRequest,
    ) -> ConceptProposalView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        staged_snapshot = job.get("staged_snapshot") or {}
        if not staged_snapshot:
            raise APIError(status_code=409, code="invalid_state", message="Import job has no staged ontology snapshot")

        proposal = (staged_snapshot.get("concept_proposals") or {}).get(proposal_id)
        if proposal is None:
            raise APIError(status_code=404, code="not_found", message="Concept proposal not found in import job")
        if str(proposal.get("status") or "") != "pending_review":
            raise APIError(
                status_code=409,
                code="invalid_state",
                message="Only pending concept proposals can be reviewed",
            )

        decision_id = str(proposal.get("decision_id") or "")
        decision = (staged_snapshot.get("normalization_decisions") or {}).get(decision_id)
        if decision is None:
            raise APIError(status_code=404, code="not_found", message="Linked normalization decision not found in import job")

        evidence_ids = [str(item) for item in proposal.get("evidence_ids") or []]
        if payload.status == "approved":
            if str(decision.get("status") or "") != "unresolved":
                raise APIError(
                    status_code=409,
                    code="invalid_state",
                    message="The linked normalization decision is no longer unresolved",
                )
            missing_evidence_ids = sorted(
                {
                    evidence_id
                    for evidence_id in evidence_ids
                    if evidence_id not in (staged_snapshot.get("evidence_sources") or {})
                }
            )
            if missing_evidence_ids:
                raise APIError(
                    status_code=409,
                    code="invalid_state",
                    message="Concept proposal references evidence that is no longer staged",
                    details=[{"field": "evidence_ids", "message": ", ".join(missing_evidence_ids)}],
                )

        now = utcnow()
        concept_id: str | None = None
        alias_id: str | None = None
        previous_status = str(proposal.get("status") or "")
        with self.store.lock():
            if payload.status == "approved":
                concept_id = f"concept_proposal_{uuid4().hex}"
                kb_version = str(
                    decision.get("kb_version")
                    or self.store.kb_versions.get(job.get("kb_version_id"), {}).get("version_code")
                    or ""
                )
                proposal["proposed_concept_id"] = concept_id
                staged_snapshot.setdefault("ontology_entities", {})[concept_id] = {
                    "entity_id": concept_id,
                    "label": proposal["concept_type"],
                    "standard_name": proposal["standard_name"],
                    "aliases": [proposal["surface_text"]],
                    "kb_version": kb_version,
                    "attributes": {
                        "definition": proposal["definition"],
                        "proposal_id": proposal_id,
                        "evidence_ids": list(evidence_ids),
                        "source_note": proposal.get("source_note"),
                    },
                }
                alias_id = f"alias_proposal_{uuid4().hex}"
                staged_snapshot.setdefault("concept_aliases", {})[alias_id] = {
                    "alias_id": alias_id,
                    "alias_text": proposal["surface_text"],
                    "concept_entity_id": concept_id,
                    "canonical_name": proposal["standard_name"],
                    "kb_version": kb_version,
                    "status": "draft",
                    "alias_type": "concept_proposal_alias",
                    "created_by": payload.operator_id,
                }
                decision["resolved_concept_id"] = concept_id
                decision["canonical_name"] = proposal["standard_name"]
                decision["candidate_list"] = [
                    {
                        "concept_id": concept_id,
                        "canonical_name": proposal["standard_name"],
                        "concept_type": proposal["concept_type"],
                        "score": 1.0,
                    }
                ]
                decision["confidence_score"] = 1.0
                decision["status"] = "resolved"
                decision["decision_reason"] = payload.reason

            proposal["status"] = payload.status
            proposal["reviewed_at"] = now
            proposal["reviewed_by"] = payload.operator_id
            proposal["review_reason"] = payload.reason
            change_id = f"chg_concept_proposal_{uuid4().hex}"
            staged_snapshot.setdefault("change_records", {})[change_id] = {
                "change_id": change_id,
                "object_type": "concept_proposal",
                "object_id": proposal_id,
                "change_type": "review",
                "from_version": previous_status,
                "to_version": payload.status,
                "change_summary": f"Concept proposal reviewed: {previous_status} -> {payload.status}",
                "reason": payload.reason,
                "impact_note": f"proposed_concept_id={concept_id};alias_id={alias_id}" if concept_id else None,
                "created_at": now,
                "created_by": payload.operator_id,
                "review_status": "approved",
            }
        self.store.persist_import_job(job)
        return self._build_concept_proposal_view(proposal, staged_snapshot)

    def batch_review_normalization_decisions(
        self,
        payload: NormalizationDecisionBatchReviewRequest,
    ) -> list[NormalizationDecisionView]:
        review_payload = NormalizationDecisionReviewRequest(
            status=payload.status,
            resolved_concept_id=payload.resolved_concept_id,
            canonical_name=payload.canonical_name,
            create_alias=payload.create_alias,
            reason=payload.reason,
            operator_id=payload.operator_id,
        )
        return [
            self.review_normalization_decision(decision_id, review_payload)
            for decision_id in payload.decision_ids
        ]

    def review_concept_alias(
        self,
        alias_id: str,
        payload: ConceptAliasReviewRequest,
    ) -> dict:
        alias = self.store.concept_aliases.get(alias_id)
        if alias is None:
            raise APIError(status_code=404, code="not_found", message="Concept alias not found")
        previous_status = str(alias.get("status") or "")
        alias["status"] = payload.status
        concept_id = str(alias.get("concept_entity_id") or alias.get("concept_id") or "")
        concept = self.store.ontology_entities.get(concept_id)
        if payload.status == "published" and concept is not None:
            aliases = list(concept.get("aliases") or [])
            alias_text = str(alias.get("alias_text") or "")
            if alias_text and alias_text not in aliases:
                aliases.append(alias_text)
                concept["aliases"] = sorted(aliases)
        change_id = f"chg_alias_{uuid4().hex}"
        self.store.change_records[change_id] = {
            "change_id": change_id,
            "object_type": "concept_alias",
            "object_id": alias_id,
            "change_type": "review",
            "from_version": previous_status,
            "to_version": payload.status,
            "change_summary": f"Concept alias reviewed: {previous_status} -> {payload.status}",
            "reason": payload.reason,
            "impact_note": f"concept_id={concept_id}" if concept_id else None,
            "created_at": utcnow(),
            "created_by": payload.operator_id,
            "review_status": "approved",
        }
        if hasattr(self.store, "persist_ontology_assets"):
            self.store.persist_ontology_assets(concept_aliases={alias_id: alias})
        return alias

    def publish_terminology_version(self, payload: TerminologyPublishRequest) -> OntologyVersionView:
        if payload.version_id in self.store.ontology_versions:
            raise APIError(status_code=409, code="version_conflict", message="Terminology version already exists")
        missing_alias_ids = [alias_id for alias_id in payload.alias_ids if alias_id not in self.store.concept_aliases]
        if missing_alias_ids:
            raise APIError(
                status_code=404,
                code="not_found",
                message=f"Concept aliases not found: {', '.join(missing_alias_ids)}",
            )
        now = utcnow()
        version = {
            "version_id": payload.version_id,
            "version_type": "terminology_resource",
            "version_name": payload.version_name,
            "based_on_version": None,
            "change_summary": payload.change_summary,
            "change_scope": ["concept_alias"],
            "created_at": now,
            "created_by": payload.operator_id,
            "review_status": "approved",
            "reviewed_by": payload.operator_id,
            "published_at": now,
            "status": "published",
        }
        for alias_id in payload.alias_ids:
            alias = self.store.concept_aliases[alias_id]
            alias["status"] = "published"
            alias["kb_version"] = payload.version_id
            concept_id = str(alias.get("concept_entity_id") or alias.get("concept_id") or "")
            concept = self.store.ontology_entities.get(concept_id)
            if concept is not None:
                aliases = list(concept.get("aliases") or [])
                alias_text = str(alias.get("alias_text") or "")
                if alias_text and alias_text not in aliases:
                    aliases.append(alias_text)
                    concept["aliases"] = sorted(aliases)
            change_id = f"chg_alias_publish_{uuid4().hex}"
            self.store.change_records[change_id] = {
                "change_id": change_id,
                "object_type": "concept_alias",
                "object_id": alias_id,
                "change_type": "publish",
                "from_version": None,
                "to_version": payload.version_id,
                "change_summary": payload.change_summary,
                "reason": payload.change_summary,
                "impact_note": f"terminology_version={payload.version_id}",
                "created_at": now,
                "created_by": payload.operator_id,
                "review_status": "approved",
            }
        self.store.ontology_versions[payload.version_id] = version
        if hasattr(self.store, "persist_ontology_assets"):
            self.store.persist_ontology_assets(
                concept_aliases={
                    alias_id: self.store.concept_aliases[alias_id]
                    for alias_id in payload.alias_ids
                }
            )
        return OntologyVersionView(**version)

    def rollback_terminology_version(self, version_id: str, *, operator_id: str = "system") -> OntologyVersionView:
        version = self.store.ontology_versions.get(version_id)
        if version is None:
            raise APIError(status_code=404, code="not_found", message="Terminology version not found")
        if version.get("version_type") != "terminology_resource":
            raise APIError(status_code=400, code="invalid_request", message="Version is not a terminology resource")
        now = utcnow()
        affected_aliases = [
            (alias_id, alias)
            for alias_id, alias in self.store.concept_aliases.items()
            if alias.get("kb_version") == version_id and alias.get("status") == "published"
        ]
        for alias_id, alias in affected_aliases:
            alias["status"] = "draft"
            concept_id = str(alias.get("concept_entity_id") or alias.get("concept_id") or "")
            concept = self.store.ontology_entities.get(concept_id)
            alias_text = str(alias.get("alias_text") or "")
            if concept is not None and alias_text:
                concept["aliases"] = [
                    item for item in (concept.get("aliases") or [])
                    if item != alias_text
                ]
            change_id = f"chg_alias_rollback_{uuid4().hex}"
            self.store.change_records[change_id] = {
                "change_id": change_id,
                "object_type": "concept_alias",
                "object_id": alias_id,
                "change_type": "rollback",
                "from_version": version_id,
                "to_version": "draft",
                "change_summary": f"Rollback terminology version {version_id}",
                "reason": f"Rollback terminology version {version_id}",
                "impact_note": f"terminology_version={version_id}",
                "created_at": now,
                "created_by": operator_id,
                "review_status": "approved",
            }
        version["status"] = "rolled_back"
        version["change_summary"] = f"{version.get('change_summary') or ''} | rolled back"
        if hasattr(self.store, "persist_ontology_assets"):
            self.store.persist_ontology_assets(
                concept_aliases={alias_id: alias for alias_id, alias in affected_aliases}
            )
        return OntologyVersionView(**version)

    def _create_alias_from_normalization_decision(
        self,
        decision: dict,
        concept: dict,
        *,
        operator_id: str,
    ) -> str | None:
        mention = self.store.mentions.get(str(decision.get("mention_id") or ""))
        if mention is None:
            return None
        alias_text = str(mention.get("surface_text") or "").strip()
        concept_id = str(concept.get("entity_id") or "")
        canonical_name = str(concept.get("standard_name") or "")
        kb_version = str(decision.get("kb_version") or concept.get("kb_version") or "")
        if not alias_text or alias_text == canonical_name:
            return None
        for alias in self.store.concept_aliases.values():
            if (
                str(alias.get("concept_entity_id") or alias.get("concept_id") or "") == concept_id
                and str(alias.get("alias_text") or "") == alias_text
                and str(alias.get("kb_version") or "") == kb_version
            ):
                return str(alias.get("alias_id"))
        alias_id = f"alias_review_{uuid4().hex}"
        self.store.concept_aliases[alias_id] = {
            "alias_id": alias_id,
            "alias_text": alias_text,
            "concept_entity_id": concept_id,
            "canonical_name": canonical_name,
            "kb_version": kb_version,
            "status": "draft",
            "alias_type": "reviewed_normalization_alias",
            "created_by": operator_id,
        }
        if hasattr(self.store, "persist_ontology_assets"):
            self.store.persist_ontology_assets(concept_aliases={alias_id: self.store.concept_aliases[alias_id]})
        return alias_id

    def _create_staged_alias_from_normalization_decision(
        self,
        staged_snapshot: dict,
        decision: dict,
        concept: dict,
        *,
        operator_id: str,
    ) -> str | None:
        mention = (staged_snapshot.get("mentions") or {}).get(str(decision.get("mention_id") or ""))
        if mention is None:
            return None
        alias_text = str(mention.get("surface_text") or "").strip()
        concept_id = str(concept.get("entity_id") or "")
        canonical_name = str(concept.get("standard_name") or "")
        kb_version = str(decision.get("kb_version") or concept.get("kb_version") or "")
        if not alias_text or alias_text == canonical_name:
            return None

        staged_aliases = staged_snapshot.setdefault("concept_aliases", {})
        for alias in staged_aliases.values():
            if (
                str(alias.get("concept_entity_id") or alias.get("concept_id") or "") == concept_id
                and str(alias.get("alias_text") or "") == alias_text
                and str(alias.get("kb_version") or "") == kb_version
            ):
                return str(alias.get("alias_id"))

        alias_id = f"alias_review_{uuid4().hex}"
        staged_aliases[alias_id] = {
            "alias_id": alias_id,
            "alias_text": alias_text,
            "concept_entity_id": concept_id,
            "canonical_name": canonical_name,
            "kb_version": kb_version,
            "status": "draft",
            "alias_type": "reviewed_normalization_alias",
            "created_by": operator_id,
        }
        return alias_id
