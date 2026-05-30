from __future__ import annotations

from uuid import UUID, uuid4

from ..exceptions import APIError
from ..schemas import KnowledgeCard, OntologyEntityView, OntologyImportCreateRequest, OntologyImportJobView
from ..store import InMemoryStore
from ..utils import utcnow


class OntologyService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

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
        self.store.persist_kb_version(version)
        self.store.persist_import_job(job)
        return OntologyImportJobView(**job)

    def get_import_job(self, import_job_id: UUID) -> OntologyImportJobView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        return OntologyImportJobView(**job)

    def publish_import_job(self, import_job_id: UUID) -> OntologyImportJobView:
        job = self.store.import_jobs.get(import_job_id)
        if job is None:
            raise APIError(status_code=404, code="not_found", message="Import job not found")
        now = utcnow()
        with self.store.lock():
            job["status"] = "published"
            job["finished_at"] = now
            kb_version = self.store.kb_versions[job["kb_version_id"]]
            kb_version["status"] = "published"
            kb_version["published_at"] = now
            kb_version["snapshot_uri"] = f"memory://{kb_version['version_code']}"
            kb_version["updated_at"] = now
        self.store.persist_import_job(job)
        self.store.persist_kb_version(kb_version)
        return OntologyImportJobView(**job)

    def get_entity(self, entity_id: str) -> OntologyEntityView:
        entity = self.store.ontology_entities.get(entity_id)
        if entity is None:
            raise APIError(status_code=404, code="not_found", message="Ontology entity not found")
        return OntologyEntityView(**entity)

    def get_knowledge_card(self, entity_id: str) -> KnowledgeCard:
        if entity_id not in self.store.ontology_entities:
            raise APIError(status_code=404, code="not_found", message="Ontology entity not found")
        card = self.store.knowledge_cards.get(entity_id)
        if card is None:
            entity = self.store.ontology_entities[entity_id]
            card = {
                "entity": {
                    "entity_id": entity["entity_id"],
                    "standard_name": entity["standard_name"],
                    "label": entity["label"],
                    "risk_level": entity.get("attributes", {}).get("risk_level", "low"),
                },
                "aliases": entity.get("aliases", []),
                "effects": [],
                "not_for_populations": [],
                "allowed_contexts": [],
                "prohibited_contexts": [],
                "contraindications": [],
                "kb_version": entity["kb_version"],
            }
        return KnowledgeCard(**card)
