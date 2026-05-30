from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from .config import Settings
from .store import InMemoryStore
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
        self._ensure_neo4j_schema()
        if self._postgres_is_empty():
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
                json_fields={"validation_report"},
            )

    def persist_batch(self, batch: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "moderation_batches",
                ["batch_id"],
                batch,
                json_fields={"request_ids"},
            )

    def persist_review_task(self, review_task: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(conn, "review_tasks", ["task_id"], review_task)

    def persist_feedback(self, feedback: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "review_feedback",
                ["feedback_id"],
                feedback,
                json_fields={"labels"},
            )

    def persist_audit_log(self, audit_log: dict[str, Any]) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "audit_logs",
                ["audit_id"],
                audit_log,
                json_fields={"change_summary"},
            )

    def persist_moderation_bundle(
        self,
        request_record: dict[str, Any],
        result_record: dict[str, Any],
        batch_record: dict[str, Any] | None,
        review_task_record: dict[str, Any] | None = None,
    ) -> None:
        with self._postgres_connection() as conn:
            self._upsert(
                conn,
                "moderation_requests",
                ["request_id"],
                request_record,
                json_fields={"metadata_json"},
            )
            self._upsert(
                conn,
                "moderation_results",
                ["result_id"],
                result_record,
                json_fields={"hit_rules", "entities", "evidence_spans", "ontology_facts"},
            )
            if batch_record is not None:
                self._upsert(
                    conn,
                    "moderation_batches",
                    ["batch_id"],
                    batch_record,
                    json_fields={"request_ids"},
                )
            if review_task_record is not None:
                self._upsert(conn, "review_tasks", ["task_id"], review_task_record)

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
            for record in seed_store.batches.values():
                self._upsert(conn, "moderation_batches", ["batch_id"], record, json_fields={"request_ids"})
            for record in seed_store.requests.values():
                self._upsert(
                    conn,
                    "moderation_requests",
                    ["request_id"],
                    record,
                    json_fields={"metadata_json"},
                )
            for record in seed_store.results.values():
                self._upsert(
                    conn,
                    "moderation_results",
                    ["result_id"],
                    record,
                    json_fields={"hit_rules", "entities", "evidence_spans", "ontology_facts"},
                )
            for record in seed_store.review_tasks.values():
                self._upsert(conn, "review_tasks", ["task_id"], record)
            for record in seed_store.feedbacks.values():
                self._upsert(conn, "review_feedback", ["feedback_id"], record, json_fields={"labels"})
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
            self.batches = self._load_table(conn, "moderation_batches", "batch_id")
            self.requests = self._load_table(conn, "moderation_requests", "request_id")
            self.results = self._load_table(conn, "moderation_results", "result_id")
            self.review_tasks = self._load_table(conn, "review_tasks", "task_id")
            self.feedbacks = self._load_table(conn, "review_feedback", "feedback_id")
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
        self.result_by_request_id = {
            record["request_id"]: result_id for result_id, record in self.results.items()
        }
        self.review_task_by_result_id = {
            record["result_id"]: task_id for task_id, record in self.review_tasks.items()
        }
        for batch in self.batches.values():
            batch["request_ids"] = [UUID(str(item)) for item in batch.get("request_ids") or []]

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

    def _replace_neo4j_graph(
        self,
        ontology_entities: dict[str, dict[str, Any]],
        knowledge_cards: dict[str, dict[str, Any]],
    ) -> None:
        driver = self._get_neo4j_driver()
        entity_rows = []
        context_index: dict[str, str] = {}
        population_index: dict[str, str] = {}
        for entity_id, entity in ontology_entities.items():
            attributes = entity.get("attributes", {})
            if attributes.get("context_name"):
                context_index[str(attributes["context_name"])] = entity_id
            if attributes.get("population_type"):
                population_index[str(attributes["population_type"])] = entity_id
            entity_rows.append(
                {
                    "entity_id": entity_id,
                    "label": entity["label"],
                    "standard_name": entity["standard_name"],
                    "aliases": entity.get("aliases", []),
                    "kb_version": entity["kb_version"],
                    "attributes_json": json.dumps(attributes, ensure_ascii=False),
                    "knowledge_card_json": json.dumps(knowledge_cards.get(entity_id), ensure_ascii=False)
                    if knowledge_cards.get(entity_id) is not None
                    else None,
                }
            )

        contra_rows = []
        prohibited_rows = []
        allowed_rows = []
        population_rows = []
        for entity_id, card in knowledge_cards.items():
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
            for context_name in card.get("prohibited_contexts", []):
                target_id = context_index.get(context_name)
                if target_id:
                    prohibited_rows.append(
                        {"source_id": entity_id, "target_id": target_id, "kb_version": kb_version}
                    )
            for context_name in card.get("allowed_contexts", []):
                target_id = context_index.get(context_name)
                if target_id:
                    allowed_rows.append(
                        {"source_id": entity_id, "target_id": target_id, "kb_version": kb_version}
                    )
            for population_name in card.get("not_for_populations", []):
                target_id = population_index.get(population_name)
                if target_id:
                    population_rows.append(
                        {"source_id": entity_id, "target_id": target_id, "kb_version": kb_version}
                    )

        with driver.session(database=self.settings.neo4j_database) as session:
            session.run("MATCH (n:Entity) DETACH DELETE n")
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
                created_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS moderation_batches (
                batch_id UUID PRIMARY KEY,
                tenant_id UUID REFERENCES tenants(tenant_id),
                client_id UUID REFERENCES api_clients(client_id),
                batch_name VARCHAR(128),
                callback_url TEXT,
                status VARCHAR(32) NOT NULL,
                total_count INTEGER NOT NULL,
                processed_count INTEGER NOT NULL,
                success_count INTEGER NOT NULL,
                failed_count INTEGER NOT NULL,
                request_ids JSONB,
                created_at TIMESTAMPTZ NOT NULL,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS moderation_requests (
                request_id UUID PRIMARY KEY,
                tenant_id UUID REFERENCES tenants(tenant_id),
                client_id UUID REFERENCES api_clients(client_id),
                batch_id UUID REFERENCES moderation_batches(batch_id),
                policy_version_id UUID REFERENCES policy_versions(policy_version_id),
                trace_id VARCHAR(64) NOT NULL,
                content_id VARCHAR(128) NOT NULL,
                request_mode VARCHAR(32) NOT NULL,
                content_type VARCHAR(64) NOT NULL,
                scenario VARCHAR(64) NOT NULL,
                content_text TEXT NOT NULL,
                content_text_hash VARCHAR(128) NOT NULL,
                metadata_json JSONB,
                idempotency_key VARCHAR(128),
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS moderation_results (
                result_id UUID PRIMARY KEY,
                request_id UUID NOT NULL UNIQUE REFERENCES moderation_requests(request_id),
                tenant_id UUID REFERENCES tenants(tenant_id),
                trace_id VARCHAR(64) NOT NULL,
                content_id VARCHAR(128) NOT NULL,
                content_text TEXT NOT NULL,
                content_type VARCHAR(64) NOT NULL,
                scenario VARCHAR(64) NOT NULL,
                kb_version_id UUID REFERENCES kb_versions(kb_version_id),
                policy_version_id UUID REFERENCES policy_versions(policy_version_id),
                decision VARCHAR(32) NOT NULL,
                risk_level VARCHAR(32) NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                recommended_action VARCHAR(64) NOT NULL,
                fallback_triggered BOOLEAN NOT NULL,
                fallback_reason TEXT,
                prompt_version VARCHAR(64),
                model_version VARCHAR(64),
                latency_ms INTEGER NOT NULL,
                explanation TEXT NOT NULL,
                hit_rules JSONB,
                entities JSONB,
                evidence_spans JSONB,
                ontology_facts JSONB,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_tasks (
                task_id UUID PRIMARY KEY,
                result_id UUID NOT NULL UNIQUE REFERENCES moderation_results(result_id),
                tenant_id UUID REFERENCES tenants(tenant_id),
                assignee_user_id UUID REFERENCES users(user_id),
                status VARCHAR(32) NOT NULL,
                queue_name VARCHAR(64),
                sla_due_at TIMESTAMPTZ,
                final_decision VARCHAR(32),
                final_action VARCHAR(64),
                overwrite_system_decision BOOLEAN NOT NULL,
                resolution_reason TEXT,
                resolution_note TEXT,
                claimed_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS review_feedback (
                feedback_id UUID PRIMARY KEY,
                task_id UUID REFERENCES review_tasks(task_id),
                result_id UUID REFERENCES moderation_results(result_id),
                tenant_id UUID REFERENCES tenants(tenant_id),
                feedback_type VARCHAR(64) NOT NULL,
                target_rule_id VARCHAR(64),
                target_entity_ref_id VARCHAR(64),
                comment TEXT,
                labels JSONB,
                created_by UUID REFERENCES users(user_id),
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
            "CREATE INDEX IF NOT EXISTS idx_moderation_results_trace_id ON moderation_results(trace_id)",
            "CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status)",
            "CREATE INDEX IF NOT EXISTS idx_moderation_requests_created_at ON moderation_requests(created_at)",
        ]
        with self._postgres_connection() as conn:
            for statement in statements:
                conn.execute(statement)

    def _ensure_neo4j_schema(self) -> None:
        driver = self._get_neo4j_driver()
        with driver.session(database=self.settings.neo4j_database) as session:
            session.run(
                "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.entity_id IS UNIQUE"
            )

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
