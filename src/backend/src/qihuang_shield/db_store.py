from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from .config import Settings
from .store import InMemoryStore
from .services.relation_schema import default_relation_schema_records
from .utils import utcnow


class DatabaseBackedStore(InMemoryStore):
    """In-memory snapshot backed by PostgreSQL and Neo4j for MVP persistence."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._neo4j_driver: Any | None = None
        super().__init__(seed_demo_data=False)
        if self.settings.db_auto_init:
            self.initialize()
        self.reload()

    def close(self) -> None:
        if self._neo4j_driver is not None:
            self._neo4j_driver.close()
            self._neo4j_driver = None

    def initialize(self) -> None:
        self._ensure_postgres_schema()
        self._ensure_postgres_compatibility_columns()
        self._ensure_neo4j_schema()
        if self._postgres_is_empty() and self.settings.enable_demo_seed:
            seed_store = InMemoryStore(seed_demo_data=True)
            self._seed_from_memory(seed_store)

    def reload(self) -> None:
        self._init_state()
        self._load_postgres_snapshot()
        self._load_neo4j_snapshot()

    def persist_user(self, user: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(conn, "users", ["user_id"], user)

    def persist_token(self, token: str, user_id: UUID) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "auth_tokens",
                ["token"],
                {"token": token, "user_id": user_id, "issued_at": utcnow()},
            )

    def persist_rule(self, rule: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(conn, "rules", ["rule_id"], rule)

    def persist_rule_version(self, rule_version: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "rule_versions",
                ["rule_version_id"],
                rule_version,
                json_fields={"conditions", "action"},
            )

    def persist_policy(self, policy: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(conn, "policies", ["policy_id"], policy)

    def persist_policy_version(self, policy_version: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "policy_versions",
                ["policy_version_id"],
                policy_version,
                json_fields={"scenario_scope", "content_type_scope", "config", "rule_overrides"},
            )

    def persist_kb_version(self, kb_version: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "kb_versions",
                ["kb_version_id"],
                kb_version,
                json_fields={"validation_report"},
            )

    def persist_import_job(self, import_job: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "ontology_import_jobs",
                ["import_job_id"],
                import_job,
                json_fields={"validation_report", "source_metadata", "staged_snapshot"},
            )

    def persist_ontology_assets(
        self,
        *,
        ontology_assertions: dict[str, dict[str, Any]] | None = None,
        evidence_sources: dict[str, dict[str, Any]] | None = None,
        concept_aliases: dict[str, dict[str, Any]] | None = None,
        guideline_documents: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        with self._postgres_connection() as conn:
            for record in (ontology_assertions or {}).values():
                self._upsert(conn, "ontology_assertions", ["assertion_id"], record, json_fields={"evidence_ids"})
            for record in (evidence_sources or {}).values():
                self._upsert(conn, "evidence_sources", ["evidence_id"], record)
            for record in (concept_aliases or {}).values():
                self._upsert(conn, "concept_aliases", ["alias_id"], record)
            for record in (guideline_documents or {}).values():
                self._upsert(conn, "guideline_documents", ["document_id"], record)

    def persist_audit_log(self, audit_log: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "audit_logs",
                ["audit_id"],
                audit_log,
                json_fields={"change_summary"},
            )

    def persist_mention_normalization_log(self, log_record: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(conn, "mention_normalization_logs", ["log_id"], log_record)

    def persist_mention(self, mention_record: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(conn, "mentions", ["mention_id"], mention_record)

    def persist_normalization_decision(self, decision_record: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "normalization_decisions",
                ["decision_id"],
                decision_record,
                json_fields={"candidate_list"},
            )

    def persist_knowledge_card_projection(self, entity_id: str, projection_record: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "knowledge_card_projections",
                ["entity_id"],
                {
                    "entity_id": entity_id,
                    "kb_version": projection_record.get("kb_version"),
                    "projection_type": projection_record.get("projection_type", "knowledge_card"),
                    "projection_version": projection_record.get("projection_version", "projection-v1"),
                    "projection_json": projection_record,
                },
                json_fields={"projection_json"},
            )

    def _seed_from_memory(self, seed_store: InMemoryStore) -> None:
        with self._postgres_connection() as conn:
            for record in seed_store.tenants.values():
                self._upsert(conn, "tenants", ["tenant_id"], record, json_fields={"config_json"})
            for record in seed_store.api_clients.values():
                self._upsert(conn, "api_clients", ["client_id"], record, json_fields={"allowed_ips"})
            for record in seed_store.users.values():
                self._upsert(conn, "users", ["user_id"], record)
            for record in seed_store.memberships.values():
                self._upsert(conn, "tenant_user_roles", ["membership_id"], record)
            for record in seed_store.rules.values():
                self._upsert(conn, "rules", ["rule_id"], record)
            for record in seed_store.rule_versions.values():
                self._upsert(
                    conn,
                    "rule_versions",
                    ["rule_version_id"],
                    record,
                    json_fields={"conditions", "action"},
                )
            for record in seed_store.policies.values():
                self._upsert(conn, "policies", ["policy_id"], record)
            for record in seed_store.policy_versions.values():
                self._upsert(
                    conn,
                    "policy_versions",
                    ["policy_version_id"],
                    record,
                    json_fields={"scenario_scope", "content_type_scope", "config", "rule_overrides"},
                )
            for record in seed_store.kb_versions.values():
                self._upsert(
                    conn,
                    "kb_versions",
                    ["kb_version_id"],
                    record,
                    json_fields={"validation_report"},
                )
            for record in seed_store.import_jobs.values():
                self._upsert(
                    conn,
                    "ontology_import_jobs",
                    ["import_job_id"],
                    record,
                    json_fields={"validation_report"},
                )
            for record in seed_store.ontology_assertions.values():
                self._upsert(conn, "ontology_assertions", ["assertion_id"], record, json_fields={"evidence_ids"})
            for record in seed_store.evidence_sources.values():
                self._upsert(conn, "evidence_sources", ["evidence_id"], record)
            for record in seed_store.concept_aliases.values():
                self._upsert(conn, "concept_aliases", ["alias_id"], record)
            for record in seed_store.guideline_documents.values():
                self._upsert(conn, "guideline_documents", ["document_id"], record)
            for record in seed_store.mentions.values():
                self._upsert(conn, "mentions", ["mention_id"], record)
            for record in seed_store.normalization_decisions.values():
                self._upsert(
                    conn,
                    "normalization_decisions",
                    ["decision_id"],
                    record,
                    json_fields={"candidate_list"},
                )
            for entity_id, record in seed_store.knowledge_card_projections.items():
                self._upsert(
                    conn,
                    "knowledge_card_projections",
                    ["entity_id"],
                    {
                        "entity_id": entity_id,
                        "kb_version": record.get("kb_version"),
                        "projection_type": record.get("projection_type", "knowledge_card"),
                        "projection_version": record.get("projection_version", "projection-v1"),
                        "projection_json": record,
                    },
                    json_fields={"projection_json"},
                )
            for record in seed_store.relation_schemas.values():
                self._upsert(
                    conn,
                    "relation_schemas",
                    ["relation_code", "schema_version"],
                    record,
                    json_fields={"subject_labels", "object_labels"},
                )
            for record in seed_store.mention_normalization_logs.values():
                self._upsert(conn, "mention_normalization_logs", ["log_id"], record)
            for record in seed_store.audit_logs.values():
                self._upsert(conn, "audit_logs", ["audit_id"], record, json_fields={"change_summary"})
            for token, user_id in seed_store.tokens.items():
                self._upsert(
                    conn,
                    "auth_tokens",
                    ["token"],
                    {"token": token, "user_id": user_id, "issued_at": utcnow()},
                )

        self._replace_neo4j_graph(seed_store.ontology_entities, seed_store.knowledge_cards)

    def _load_postgres_snapshot(self) -> None:
        with self._postgres_connection() as conn:
            self.tenants = self._load_table(conn, "tenants", "tenant_id")
            self.api_clients = self._load_table(conn, "api_clients", "client_id")
            self.users = self._load_table(conn, "users", "user_id")
            self.memberships = self._load_table(conn, "tenant_user_roles", "membership_id")
            self.rules = self._load_table(conn, "rules", "rule_id")
            self.rule_versions = self._load_table(conn, "rule_versions", "rule_version_id")
            self.policies = self._load_table(conn, "policies", "policy_id")
            self.policy_versions = self._load_table(conn, "policy_versions", "policy_version_id")
            self.kb_versions = self._load_table(conn, "kb_versions", "kb_version_id")
            self.import_jobs = self._load_table(conn, "ontology_import_jobs", "import_job_id")
            self.ontology_assertions = self._load_table(conn, "ontology_assertions", "assertion_id")
            self.evidence_sources = self._load_table(conn, "evidence_sources", "evidence_id")
            self.concept_aliases = self._load_table(conn, "concept_aliases", "alias_id")
            self.guideline_documents = self._load_table(conn, "guideline_documents", "document_id")
            self.mentions = self._load_table(conn, "mentions", "mention_id")
            self.normalization_decisions = self._load_table(conn, "normalization_decisions", "decision_id")
            projection_rows = self._load_table(conn, "knowledge_card_projections", "entity_id")
            self.knowledge_card_projections = {
                key: value.get("projection_json", value)
                for key, value in projection_rows.items()
            }
            self.relation_schemas = self._load_relation_schemas(conn)
            self.mention_normalization_logs = self._load_table(conn, "mention_normalization_logs", "log_id")
            self.audit_logs = self._load_table(conn, "audit_logs", "audit_id")
            token_rows = conn.execute("SELECT token, user_id FROM auth_tokens").fetchall()
            self.tokens = {row["token"]: row["user_id"] for row in token_rows}

        self.tenant_code_index = {
            record["tenant_code"]: tenant_id for tenant_id, record in self.tenants.items()
        }
        self.user_email_index = {
            record["email"]: user_id for user_id, record in self.users.items()
        }
        self.rule_code_index = {
            record["rule_code"]: rule_id for rule_id, record in self.rules.items()
        }
        self.policy_code_index = {
            record["policy_code"]: policy_id for policy_id, record in self.policies.items()
        }
    def _load_neo4j_snapshot(self) -> None:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.settings.neo4j_database) as session:
            rows = session.run(
                """
                MATCH (e:Entity)
                RETURN e.entity_id AS entity_id,
                       e.label AS label,
                       e.standard_name AS standard_name,
                       e.aliases AS aliases,
                       e.kb_version AS kb_version,
                       e.attributes_json AS attributes_json,
                       e.knowledge_card_json AS knowledge_card_json
                ORDER BY e.entity_id
                """
            )
            for row in rows:
                entity = {
                    "entity_id": row["entity_id"],
                    "label": row["label"],
                    "standard_name": row["standard_name"],
                    "aliases": row["aliases"] or [],
                    "kb_version": row["kb_version"],
                    "attributes": json.loads(row["attributes_json"] or "{}"),
                }
                self.ontology_entities[entity["entity_id"]] = entity
                if row["knowledge_card_json"]:
                    self.knowledge_cards[entity["entity_id"]] = json.loads(row["knowledge_card_json"])

    def _build_neo4j_entity_rows(
        self,
        entity_ids: set[str],
        ontology_entities: dict[str, dict[str, Any]],
        knowledge_cards: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for entity_id in sorted(entity_ids):
            entity = ontology_entities.get(entity_id)
            if entity is None:
                continue
            rows.append(
                {
                    "entity_id": entity_id,
                    "label": entity["label"],
                    "standard_name": entity["standard_name"],
                    "aliases": entity.get("aliases", []),
                    "kb_version": entity["kb_version"],
                    "attributes_json": json.dumps(entity.get("attributes", {}), ensure_ascii=False),
                    "knowledge_card_json": json.dumps(knowledge_cards.get(entity_id), ensure_ascii=False)
                    if knowledge_cards.get(entity_id) is not None
                    else None,
                }
            )
        return rows

    def _build_neo4j_relationship_rows(
        self,
        source_entity_ids: set[str],
        ontology_entities: dict[str, dict[str, Any]],
        knowledge_cards: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        context_index: dict[str, str] = {}
        population_index: dict[str, str] = {}
        effect_index: dict[str, str] = {}
        for entity_id, entity in ontology_entities.items():
            attributes = entity.get("attributes", {})
            if attributes.get("context_name"):
                context_index[str(attributes["context_name"])] = entity_id
            if attributes.get("population_type"):
                population_index[str(attributes["population_type"])] = entity_id
            if attributes.get("effect_name"):
                effect_index[str(attributes["effect_name"])] = entity_id

        contra_rows: list[dict[str, Any]] = []
        prohibited_rows: list[dict[str, Any]] = []
        allowed_rows: list[dict[str, Any]] = []
        population_rows: list[dict[str, Any]] = []
        effect_rows: list[dict[str, Any]] = []
        referenced_target_ids: set[str] = set()

        for entity_id in sorted(source_entity_ids):
            card = knowledge_cards.get(entity_id)
            if card is None:
                continue
            kb_version = card.get("kb_version")
            for item in card.get("contraindications", []):
                target_entity_id = item.get("target_entity_id")
                if target_entity_id:
                    contra_rows.append(
                        {
                            "source_id": entity_id,
                            "target_id": target_entity_id,
                            "kb_version": kb_version,
                            "relation": item.get("relation", "CONTRAINDICATED_WITH"),
                        }
                    )
                    referenced_target_ids.add(target_entity_id)
            for context_name in card.get("prohibited_contexts", []):
                target_id = context_index.get(context_name)
                if target_id:
                    prohibited_rows.append(
                        {"source_id": entity_id, "target_id": target_id, "kb_version": kb_version}
                    )
                    referenced_target_ids.add(target_id)
            for context_name in card.get("allowed_contexts", []):
                target_id = context_index.get(context_name)
                if target_id:
                    allowed_rows.append(
                        {"source_id": entity_id, "target_id": target_id, "kb_version": kb_version}
                    )
                    referenced_target_ids.add(target_id)
            for population_name in card.get("not_for_populations", []):
                target_id = population_index.get(population_name)
                if target_id:
                    population_rows.append(
                        {"source_id": entity_id, "target_id": target_id, "kb_version": kb_version}
                    )
                    referenced_target_ids.add(target_id)
            for effect_name in card.get("effects", []):
                target_id = effect_index.get(effect_name)
                if target_id:
                    effect_rows.append(
                        {"source_id": entity_id, "target_id": target_id, "kb_version": kb_version}
                    )
                    referenced_target_ids.add(target_id)

        return {
            "contra_rows": contra_rows,
            "prohibited_rows": prohibited_rows,
            "allowed_rows": allowed_rows,
            "population_rows": population_rows,
            "effect_rows": effect_rows,
            "target_entity_ids": referenced_target_ids,
        }

    def _upsert_neo4j_entities(self, session: Any, entity_rows: list[dict[str, Any]]) -> None:
        if not entity_rows:
            return
        session.run(
            """
            UNWIND $rows AS row
            MERGE (e:Entity {entity_id: row.entity_id})
            SET e.label = row.label,
                e.standard_name = row.standard_name,
                e.aliases = row.aliases,
                e.kb_version = row.kb_version,
                e.attributes_json = row.attributes_json,
                e.knowledge_card_json = row.knowledge_card_json
            """,
            rows=entity_rows,
        )

    def _delete_managed_neo4j_relationships(self, session: Any, source_entity_ids: set[str]) -> None:
        if not source_entity_ids:
            return
        session.run(
            """
            UNWIND $rows AS row
            MATCH (s:Entity {entity_id: row.source_id})-[r]->()
            WHERE type(r) IN $relation_types
            DELETE r
            """,
            rows=[{"source_id": entity_id} for entity_id in sorted(source_entity_ids)],
            relation_types=[
                "CONTRAINDICATED_WITH",
                "PROHIBITED_IN_CONTEXT",
                "ALLOWED_IN_CONTEXT",
                "NOT_FOR_POPULATION",
                "HAS_EFFECT",
                "SUBJECT_OF",
                "ASSERTS_OBJECT",
                "SUPPORTED_BY",
                "EXTRACTED_FROM",
            ],
        )

    def _build_neo4j_provenance_rows(self, source_entity_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
        return self.build_neo4j_provenance_rows(source_entity_ids)

    def _upsert_neo4j_relationships(self, session: Any, relationship_rows: dict[str, Any]) -> None:
        contra_rows = relationship_rows["contra_rows"]
        prohibited_rows = relationship_rows["prohibited_rows"]
        allowed_rows = relationship_rows["allowed_rows"]
        population_rows = relationship_rows["population_rows"]
        effect_rows = relationship_rows["effect_rows"]

        if contra_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {entity_id: row.source_id})
                MATCH (t:Entity {entity_id: row.target_id})
                MERGE (s)-[r:CONTRAINDICATED_WITH]->(t)
                SET r.kb_version = row.kb_version,
                    r.relation = row.relation
                """,
                rows=contra_rows,
            )
        if prohibited_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {entity_id: row.source_id})
                MATCH (t:Entity {entity_id: row.target_id})
                MERGE (s)-[r:PROHIBITED_IN_CONTEXT]->(t)
                SET r.kb_version = row.kb_version
                """,
                rows=prohibited_rows,
            )
        if allowed_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {entity_id: row.source_id})
                MATCH (t:Entity {entity_id: row.target_id})
                MERGE (s)-[r:ALLOWED_IN_CONTEXT]->(t)
                SET r.kb_version = row.kb_version
                """,
                rows=allowed_rows,
            )
        if population_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {entity_id: row.source_id})
                MATCH (t:Entity {entity_id: row.target_id})
                MERGE (s)-[r:NOT_FOR_POPULATION]->(t)
                SET r.kb_version = row.kb_version
                """,
                rows=population_rows,
            )
        if effect_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (s:Entity {entity_id: row.source_id})
                MATCH (t:Entity {entity_id: row.target_id})
                MERGE (s)-[r:HAS_EFFECT]->(t)
                SET r.kb_version = row.kb_version
                """,
                rows=effect_rows,
            )

    def _upsert_neo4j_provenance(self, session: Any, provenance_rows: dict[str, list[dict[str, Any]]]) -> None:
        assertion_rows = provenance_rows["assertion_rows"]
        evidence_rows = provenance_rows["evidence_rows"]
        document_rows = provenance_rows["document_rows"]
        support_rows = provenance_rows["support_rows"]
        document_link_rows = provenance_rows["document_link_rows"]
        object_rows = provenance_rows["object_rows"]

        if document_rows:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (d:GuidelineDocument {document_id: row.document_id})
                SET d.kb_version = row.kb_version,
                    d.source_uri = row.source_uri,
                    d.title = row.title,
                    d.source_type = row.source_type,
                    d.status = row.status
                """,
                rows=document_rows,
            )
        if evidence_rows:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (ev:EvidenceSource {evidence_id: row.evidence_id})
                SET ev.kb_version = row.kb_version,
                    ev.source_type = row.source_type,
                    ev.source_uri = row.source_uri,
                    ev.source_title = row.source_title,
                    ev.source_text = row.source_text,
                    ev.entity_id = row.entity_id,
                    ev.status = row.status,
                    ev.document_id = row.document_id
                WITH ev, row
                OPTIONAL MATCH (d:GuidelineDocument {document_id: row.document_id})
                FOREACH (_ IN CASE WHEN d IS NULL THEN [] ELSE [1] END |
                    MERGE (ev)-[:EXTRACTED_FROM]->(d)
                )
                """,
                rows=evidence_rows,
            )
        if assertion_rows:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (a:Assertion {assertion_id: row.assertion_id})
                SET a.subject_entity_id = row.subject_entity_id,
                    a.predicate_type = row.predicate_type,
                    a.object_entity_id = row.object_entity_id,
                    a.object_value = row.object_value,
                    a.kb_version = row.kb_version,
                    a.status = row.status,
                    a.document_id = row.document_id
                WITH a, row
                MATCH (s:Entity {entity_id: row.subject_entity_id})
                MERGE (s)-[:SUBJECT_OF]->(a)
                """,
                rows=assertion_rows,
            )
        if object_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Assertion {assertion_id: row.assertion_id})
                MATCH (o:Entity {entity_id: row.object_entity_id})
                MERGE (a)-[:ASSERTS_OBJECT]->(o)
                """,
                rows=object_rows,
            )
        if support_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Assertion {assertion_id: row.assertion_id})
                MATCH (ev:EvidenceSource {evidence_id: row.evidence_id})
                MERGE (a)-[:SUPPORTED_BY]->(ev)
                """,
                rows=support_rows,
            )
        if document_link_rows:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (a:Assertion {assertion_id: row.assertion_id})
                MATCH (d:GuidelineDocument {document_id: row.document_id})
                MERGE (a)-[:EXTRACTED_FROM]->(d)
                """,
                rows=document_link_rows,
            )

    def _upsert_neo4j_subgraph(
        self,
        changed_entity_ids: set[str],
        changed_knowledge_card_ids: set[str] | None = None,
    ) -> None:
        source_entity_ids = {
            entity_id
            for entity_id in (changed_knowledge_card_ids or set())
            if entity_id in self.knowledge_card_projections
        }
        relationship_rows = self._build_neo4j_relationship_rows(
            source_entity_ids,
            self.ontology_entities,
            self.knowledge_card_projections,
        )
        provenance_rows = self._build_neo4j_provenance_rows(source_entity_ids)
        required_entity_ids = set(changed_entity_ids) | source_entity_ids | relationship_rows["target_entity_ids"]
        entity_rows = self._build_neo4j_entity_rows(
            required_entity_ids,
            self.ontology_entities,
            self.knowledge_card_projections,
        )

        if not entity_rows and not source_entity_ids:
            return

        driver = self._get_neo4j_driver()
        with driver.session(database=self.settings.neo4j_database) as session:
            self._upsert_neo4j_entities(session, entity_rows)
            self._delete_managed_neo4j_relationships(session, source_entity_ids)
            self._upsert_neo4j_relationships(session, relationship_rows)
            self._upsert_neo4j_provenance(session, provenance_rows)

    def _replace_neo4j_graph(
        self,
        ontology_entities: dict[str, dict[str, Any]],
        knowledge_cards: dict[str, dict[str, Any]],
    ) -> None:
        driver = self._get_neo4j_driver()
        relationship_rows = self._build_neo4j_relationship_rows(
            set(knowledge_cards.keys()),
            ontology_entities,
            knowledge_cards,
        )
        provenance_rows = self._build_neo4j_provenance_rows(set(knowledge_cards.keys()))
        entity_rows = self._build_neo4j_entity_rows(
            set(ontology_entities.keys()) | relationship_rows["target_entity_ids"],
            ontology_entities,
            knowledge_cards,
        )

        with driver.session(database=self.settings.neo4j_database) as session:
            session.run("MATCH (n) WHERE n:Entity OR n:Assertion OR n:EvidenceSource OR n:GuidelineDocument DETACH DELETE n")
            self._upsert_neo4j_entities(session, entity_rows)
            self._upsert_neo4j_relationships(session, relationship_rows)
            self._upsert_neo4j_provenance(session, provenance_rows)

    def _ensure_postgres_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id UUID PRIMARY KEY,
                tenant_code VARCHAR(64) NOT NULL UNIQUE,
                tenant_name VARCHAR(128) NOT NULL,
                status VARCHAR(32) NOT NULL,
                config_json JSONB,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS api_clients (
                client_id UUID PRIMARY KEY,
                tenant_id UUID REFERENCES tenants(tenant_id),
                client_key VARCHAR(128) NOT NULL UNIQUE,
                client_secret_hash VARCHAR(256),
                client_name VARCHAR(128),
                auth_mode VARCHAR(32),
                allowed_ips JSONB,
                status VARCHAR(32) NOT NULL,
                last_used_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id UUID PRIMARY KEY,
                email VARCHAR(256) NOT NULL UNIQUE,
                display_name VARCHAR(128) NOT NULL,
                password VARCHAR(256) NOT NULL,
                status VARCHAR(32) NOT NULL,
                last_login_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tenant_user_roles (
                membership_id UUID PRIMARY KEY,
                tenant_id UUID REFERENCES tenants(tenant_id),
                user_id UUID REFERENCES users(user_id),
                role_code VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS rules (
                rule_id UUID PRIMARY KEY,
                rule_code VARCHAR(32) NOT NULL UNIQUE,
                rule_name VARCHAR(128) NOT NULL,
                rule_type VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                description TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS rule_versions (
                rule_version_id UUID PRIMARY KEY,
                rule_id UUID REFERENCES rules(rule_id),
                version_no VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                priority INTEGER NOT NULL,
                default_decision VARCHAR(32) NOT NULL,
                risk_level VARCHAR(32) NOT NULL,
                conditions JSONB,
                action JSONB,
                explanation_template TEXT NOT NULL,
                published_by UUID,
                published_at TIMESTAMPTZ,
                rollback_from_version_id UUID,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS policies (
                policy_id UUID PRIMARY KEY,
                tenant_id UUID REFERENCES tenants(tenant_id),
                policy_code VARCHAR(64) NOT NULL UNIQUE,
                policy_name VARCHAR(128) NOT NULL,
                status VARCHAR(32) NOT NULL,
                description TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS policy_versions (
                policy_version_id UUID PRIMARY KEY,
                policy_id UUID REFERENCES policies(policy_id),
                version_no INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL,
                scenario_scope JSONB,
                content_type_scope JSONB,
                fallback_mode VARCHAR(64) NOT NULL,
                low_confidence_decision VARCHAR(32) NOT NULL,
                config JSONB,
                rule_overrides JSONB,
                published_by UUID,
                published_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS kb_versions (
                kb_version_id UUID PRIMARY KEY,
                version_code VARCHAR(64) NOT NULL UNIQUE,
                status VARCHAR(32) NOT NULL,
                source_type VARCHAR(64) NOT NULL,
                source_checksum VARCHAR(128),
                validation_report JSONB,
                snapshot_uri VARCHAR(256),
                published_by UUID,
                published_at TIMESTAMPTZ,
                rollback_from_version_id UUID,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ontology_import_jobs (
                import_job_id UUID PRIMARY KEY,
                kb_version_id UUID REFERENCES kb_versions(kb_version_id),
                status VARCHAR(32) NOT NULL,
                source_uri TEXT NOT NULL,
                source_type VARCHAR(64) NOT NULL,
                warning_count INTEGER NOT NULL,
                error_count INTEGER NOT NULL,
                validation_report JSONB,
                staged_snapshot JSONB,
                created_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ontology_assertions (
                assertion_id VARCHAR(64) PRIMARY KEY,
                subject_entity_id VARCHAR(64) NOT NULL,
                predicate_type VARCHAR(64) NOT NULL,
                object_entity_id VARCHAR(64),
                object_value TEXT,
                kb_version VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                evidence_ids JSONB,
                document_id VARCHAR(64),
                source_guide TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence_sources (
                evidence_id VARCHAR(64) PRIMARY KEY,
                kb_version VARCHAR(64) NOT NULL,
                source_type VARCHAR(64) NOT NULL,
                source_uri TEXT,
                source_title TEXT,
                source_text TEXT NOT NULL,
                entity_id VARCHAR(64),
                status VARCHAR(32) NOT NULL,
                document_id VARCHAR(64)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS concept_aliases (
                alias_id VARCHAR(64) PRIMARY KEY,
                alias_text VARCHAR(128) NOT NULL,
                concept_entity_id VARCHAR(64) NOT NULL,
                canonical_name VARCHAR(128) NOT NULL,
                kb_version VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                alias_type VARCHAR(64)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS guideline_documents (
                document_id VARCHAR(64) PRIMARY KEY,
                kb_version VARCHAR(64) NOT NULL,
                source_uri TEXT,
                title TEXT,
                source_type VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS relation_schemas (
                relation_code VARCHAR(64) NOT NULL,
                schema_version VARCHAR(64) NOT NULL,
                subject_labels JSONB NOT NULL,
                object_labels JSONB NOT NULL,
                evidence_required BOOLEAN NOT NULL,
                application_relevant BOOLEAN NOT NULL,
                status VARCHAR(32) NOT NULL,
                PRIMARY KEY (relation_code, schema_version)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mentions (
                mention_id VARCHAR(64) PRIMARY KEY,
                source_type VARCHAR(64) NOT NULL,
                source_record_id VARCHAR(128) NOT NULL,
                surface_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                start_offset INTEGER NOT NULL,
                end_offset INTEGER NOT NULL,
                mention_type_guess VARCHAR(64),
                context_window TEXT,
                kb_version VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS normalization_decisions (
                decision_id VARCHAR(64) PRIMARY KEY,
                mention_id VARCHAR(64) REFERENCES mentions(mention_id),
                resolved_concept_id VARCHAR(64),
                canonical_name TEXT,
                resolver_type VARCHAR(64) NOT NULL,
                resolver_version VARCHAR(64) NOT NULL,
                confidence_score DOUBLE PRECISION NOT NULL,
                candidate_list JSONB,
                decision_reason TEXT,
                status VARCHAR(32) NOT NULL,
                kb_version VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ontology_versions_registry (
                version_id VARCHAR(64) PRIMARY KEY,
                version_type VARCHAR(32) NOT NULL,
                version_name VARCHAR(255) NOT NULL,
                based_on_version VARCHAR(64),
                change_summary TEXT,
                change_scope_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                created_by VARCHAR(64) NOT NULL,
                review_status VARCHAR(32) NOT NULL,
                reviewed_by VARCHAR(64),
                published_at TIMESTAMPTZ,
                status VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS relation_definitions_registry (
                relation_code VARCHAR(64) PRIMARY KEY,
                display_name_zh VARCHAR(255) NOT NULL,
                definition TEXT NOT NULL,
                domain_json JSONB NOT NULL,
                range_json JSONB NOT NULL,
                semantic_direction TEXT,
                inverse_relation VARCHAR(64),
                boundary_note TEXT,
                condition_note TEXT,
                schema_version VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS condition_sets (
                condition_set_id VARCHAR(64) PRIMARY KEY,
                logic_json JSONB NOT NULL,
                note TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS evidence_links (
                link_id VARCHAR(64) PRIMARY KEY,
                target_type VARCHAR(64) NOT NULL,
                target_id VARCHAR(64) NOT NULL,
                evidence_id VARCHAR(64) NOT NULL REFERENCES evidence_sources(evidence_id),
                support_role VARCHAR(64) NOT NULL,
                support_strength VARCHAR(32) NOT NULL,
                note TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS change_records_registry (
                change_id VARCHAR(64) PRIMARY KEY,
                object_type VARCHAR(64) NOT NULL,
                object_id VARCHAR(64) NOT NULL,
                change_type VARCHAR(32) NOT NULL,
                from_version VARCHAR(64),
                to_version VARCHAR(64) NOT NULL,
                change_summary TEXT NOT NULL,
                reason TEXT,
                impact_note TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                created_by VARCHAR(64) NOT NULL,
                review_status VARCHAR(32) NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS knowledge_card_projections (
                entity_id VARCHAR(64) PRIMARY KEY,
                kb_version VARCHAR(64),
                projection_type VARCHAR(64) NOT NULL,
                projection_version VARCHAR(64) NOT NULL,
                projection_json JSONB NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS mention_normalization_logs (
                log_id VARCHAR(64) PRIMARY KEY,
                request_id UUID,
                result_id UUID,
                tenant_id UUID REFERENCES tenants(tenant_id),
                trace_id VARCHAR(64) NOT NULL,
                mention_text TEXT NOT NULL,
                normalized_concept_id VARCHAR(64),
                canonical_name TEXT,
                normalization_method VARCHAR(64) NOT NULL,
                confidence_score DOUBLE PRECISION NOT NULL,
                source_content_id VARCHAR(128),
                kb_version VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                audit_id UUID PRIMARY KEY,
                tenant_id UUID REFERENCES tenants(tenant_id),
                actor_type VARCHAR(32) NOT NULL,
                actor_user_id UUID,
                actor_client_id UUID,
                action VARCHAR(128) NOT NULL,
                resource_type VARCHAR(64) NOT NULL,
                resource_id VARCHAR(128) NOT NULL,
                change_summary JSONB,
                trace_id VARCHAR(64),
                ip_address VARCHAR(64),
                user_agent TEXT,
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS auth_tokens (
                token TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(user_id),
                issued_at TIMESTAMPTZ NOT NULL
            )
            """,
        ]
        with self._postgres_connection() as conn:
            for statement in statements:
                conn.execute(statement)

    def _ensure_postgres_compatibility_columns(self) -> None:
        with self._postgres_connection() as conn:
            conn.execute(
                "ALTER TABLE ontology_import_jobs ADD COLUMN IF NOT EXISTS staged_snapshot JSONB"
            )
            for record in self.relation_schemas.values():
                self._upsert(
                    conn,
                    "relation_schemas",
                    ["relation_code", "schema_version"],
                    record,
                    json_fields={"subject_labels", "object_labels"},
                )

    def _ensure_neo4j_schema(self) -> None:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.settings.neo4j_database) as session:
            session.run(
                "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT assertion_id_unique IF NOT EXISTS FOR (a:Assertion) REQUIRE a.assertion_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT evidence_id_unique IF NOT EXISTS FOR (ev:EvidenceSource) REQUIRE ev.evidence_id IS UNIQUE"
            )
            session.run(
                "CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:GuidelineDocument) REQUIRE d.document_id IS UNIQUE"
            )
            # Full-text index for candidate entity matching (PRD 5.2)
            try:
                session.run(
                    "CREATE FULLTEXT INDEX entity_fulltext IF NOT EXISTS "
                    "FOR (e:Entity) ON EACH [e.standard_name]"
                )
            except Exception:
                pass  # Neo4j Community Edition may not support full-text indexes

    def _postgres_is_empty(self) -> bool:
        with self._postgres_connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM tenants").fetchone()
            return bool(row and row["count"] == 0)

    def _load_table(
        self,
        conn: Any,
        table_name: str,
        key_field: str,
    ) -> dict[Any, dict[str, Any]]:
        rows = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        return {row[key_field]: dict(row) for row in rows}

    def _load_relation_schemas(self, conn: Any) -> dict[str, dict[str, Any]]:
        rows = conn.execute("SELECT * FROM relation_schemas").fetchall()
        records = {row["relation_code"]: dict(row) for row in rows}
        return records or default_relation_schema_records()

    def _upsert(
        self,
        conn: Any,
        table_name: str,
        conflict_columns: list[str],
        record: dict[str, Any],
        json_fields: set[str] | None = None,
    ) -> None:
        json_fields = json_fields or set()
        columns = list(record.keys())
        placeholders = ", ".join(["%s"] * len(columns))
        update_columns = [column for column in columns if column not in conflict_columns]
        update_clause = ", ".join([f"{column} = EXCLUDED.{column}" for column in update_columns])
        sql = (
            f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT ({', '.join(conflict_columns)}) DO UPDATE SET {update_clause}"
        )
        values = [self._adapt_value(column, record.get(column), json_fields) for column in columns]
        conn.execute(sql, values)

    def _adapt_value(self, column: str, value: Any, json_fields: set[str]) -> Any:
        if column not in json_fields:
            return value
        if value is None:
            return None
        from psycopg.types.json import Jsonb

        return Jsonb(self._json_ready(value))

    def _json_ready(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): self._json_ready(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_ready(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_ready(item) for item in value]
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        return value

    def _postgres_connection(self) -> Any:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requires psycopg. Run `uv sync --extra dev` in src/backend first."
            ) from exc
        return psycopg.connect(self.settings.postgres_dsn, row_factory=dict_row)

    def _get_neo4j_driver(self) -> Any:
        if self._neo4j_driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise RuntimeError(
                    "Neo4j backend requires neo4j driver. Run `uv sync --extra dev` in src/backend first."
                ) from exc
            self._neo4j_driver = GraphDatabase.driver(
                self.settings.neo4j_uri,
                auth=(self.settings.neo4j_user, self.settings.neo4j_password),
            )
        return self._neo4j_driver
