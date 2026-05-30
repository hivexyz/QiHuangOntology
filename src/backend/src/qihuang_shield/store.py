from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from .enums import (
    Decision,
    FeedbackType,
    ReviewTaskStatus,
    RiskLevel,
    RoleCode,
    RuleType,
    Scenario,
)
from .utils import utcnow


class InMemoryStore:
    """Simple in-memory store for MVP scaffolding and local development."""

    def __init__(self, *, seed_demo_data: bool = True) -> None:
        self._lock = RLock()
        self._init_state()
        if seed_demo_data:
            self._seed_demo_data()

    def _init_state(self) -> None:
        self.tenants: dict[UUID, dict[str, Any]] = {}
        self.tenant_code_index: dict[str, UUID] = {}
        self.api_clients: dict[UUID, dict[str, Any]] = {}
        self.users: dict[UUID, dict[str, Any]] = {}
        self.user_email_index: dict[str, UUID] = {}
        self.memberships: dict[UUID, dict[str, Any]] = {}
        self.rules: dict[UUID, dict[str, Any]] = {}
        self.rule_code_index: dict[str, UUID] = {}
        self.rule_versions: dict[UUID, dict[str, Any]] = {}
        self.policies: dict[UUID, dict[str, Any]] = {}
        self.policy_code_index: dict[str, UUID] = {}
        self.policy_versions: dict[UUID, dict[str, Any]] = {}
        self.kb_versions: dict[UUID, dict[str, Any]] = {}
        self.import_jobs: dict[UUID, dict[str, Any]] = {}
        self.ontology_entities: dict[str, dict[str, Any]] = {}
        self.knowledge_cards: dict[str, dict[str, Any]] = {}
        self.batches: dict[UUID, dict[str, Any]] = {}
        self.requests: dict[UUID, dict[str, Any]] = {}
        self.results: dict[UUID, dict[str, Any]] = {}
        self.result_by_request_id: dict[UUID, UUID] = {}
        self.review_tasks: dict[UUID, dict[str, Any]] = {}
        self.review_task_by_result_id: dict[UUID, UUID] = {}
        self.feedbacks: dict[UUID, dict[str, Any]] = {}
        self.audit_logs: dict[UUID, dict[str, Any]] = {}
        self.tokens: dict[str, UUID] = {}

    def lock(self) -> RLock:
        return self._lock

    def snapshot(self, value: Any) -> Any:
        return deepcopy(value)

    def close(self) -> None:
        return None

    def persist_user(self, _: dict[str, Any]) -> None:
        return None

    def persist_token(self, _: str, __: UUID) -> None:
        return None

    def persist_rule(self, _: dict[str, Any]) -> None:
        return None

    def persist_rule_version(self, _: dict[str, Any]) -> None:
        return None

    def persist_policy(self, _: dict[str, Any]) -> None:
        return None

    def persist_policy_version(self, _: dict[str, Any]) -> None:
        return None

    def persist_kb_version(self, _: dict[str, Any]) -> None:
        return None

    def persist_import_job(self, _: dict[str, Any]) -> None:
        return None

    def persist_batch(self, _: dict[str, Any]) -> None:
        return None

    def persist_review_task(self, _: dict[str, Any]) -> None:
        return None

    def persist_feedback(self, _: dict[str, Any]) -> None:
        return None

    def persist_audit_log(self, _: dict[str, Any]) -> None:
        return None

    def persist_moderation_bundle(
        self,
        _: dict[str, Any],
        __: dict[str, Any],
        ___: dict[str, Any],
        ____: dict[str, Any] | None = None,
    ) -> None:
        return None

    def _seed_demo_data(self) -> None:
        now = utcnow()
        tenant_id = uuid4()
        self.tenants[tenant_id] = {
            "tenant_id": tenant_id,
            "tenant_code": "tenant_demo",
            "tenant_name": "Demo Tenant",
            "status": "active",
            "config_json": {},
            "created_at": now,
            "updated_at": now,
        }
        self.tenant_code_index["tenant_demo"] = tenant_id

        client_id = uuid4()
        self.api_clients[client_id] = {
            "client_id": client_id,
            "tenant_id": tenant_id,
            "client_key": "demo-client",
            "client_secret_hash": "demo-secret-hash",
            "client_name": "Demo Client",
            "auth_mode": "aksk",
            "allowed_ips": [],
            "status": "active",
            "last_used_at": None,
            "created_at": now,
            "updated_at": now,
        }

        admin_id = uuid4()
        reviewer_id = uuid4()
        self.users[admin_id] = {
            "user_id": admin_id,
            "email": "admin@example.com",
            "display_name": "Admin User",
            "password": "password123",
            "status": "active",
            "last_login_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.users[reviewer_id] = {
            "user_id": reviewer_id,
            "email": "reviewer@example.com",
            "display_name": "Reviewer User",
            "password": "password123",
            "status": "active",
            "last_login_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.user_email_index["admin@example.com"] = admin_id
        self.user_email_index["reviewer@example.com"] = reviewer_id

        for user_id, role_code in ((admin_id, RoleCode.ADMIN.value), (reviewer_id, RoleCode.REVIEWER.value)):
            membership_id = uuid4()
            self.memberships[membership_id] = {
                "membership_id": membership_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "role_code": role_code,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }

        kb_version_id = uuid4()
        self.kb_versions[kb_version_id] = {
            "kb_version_id": kb_version_id,
            "version_code": "kb-2026-05-29-01",
            "status": "published",
            "source_type": "mixed",
            "source_checksum": None,
            "validation_report": {"warnings": 0, "errors": 0},
            "snapshot_uri": "memory://kb-2026-05-29-01",
            "published_by": admin_id,
            "published_at": now,
            "rollback_from_version_id": None,
            "created_at": now,
            "updated_at": now,
        }

        rules_seed = [
            ("R001", "药食同源/原料身份校验", RuleType.MATERIAL_IDENTITY, "高风险药材用于食疗/茶饮场景"),
            ("R002", "配伍禁忌校验", RuleType.CONTRAINDICATION, "命中配伍禁忌关系"),
            ("R003", "功效宣称越界", RuleType.EFFECT_CLAIM, "普通食疗/茶饮内容宣称治疗疾病"),
            ("R004", "特殊人群长期服用风险", RuleType.POPULATION_RISK, "特殊人群长期服用风险提示"),
        ]
        for idx, (code, name, rule_type, description) in enumerate(rules_seed, start=1):
            rule_id = uuid4()
            rule_version_id = uuid4()
            self.rules[rule_id] = {
                "rule_id": rule_id,
                "rule_code": code,
                "rule_name": name,
                "rule_type": rule_type.value,
                "status": "active",
                "description": description,
                "created_at": now,
                "updated_at": now,
            }
            self.rule_code_index[code] = rule_id
            default_decision = Decision.BLOCK if code in {"R001", "R003"} else Decision.REVIEW
            risk_level = RiskLevel.HIGH if code in {"R001", "R002", "R003"} else RiskLevel.MEDIUM
            self.rule_versions[rule_version_id] = {
                "rule_version_id": rule_version_id,
                "rule_id": rule_id,
                "version_no": "1.0.0",
                "status": "published",
                "priority": 100 - idx,
                "default_decision": default_decision.value,
                "risk_level": risk_level.value,
                "conditions": {},
                "action": {},
                "explanation_template": description,
                "published_by": admin_id,
                "published_at": now,
                "rollback_from_version_id": None,
                "created_at": now,
                "updated_at": now,
            }

        policy_id = uuid4()
        policy_version_id = uuid4()
        self.policies[policy_id] = {
            "policy_id": policy_id,
            "tenant_id": tenant_id,
            "policy_code": "pol_default_cn",
            "policy_name": "默认中文健康内容策略",
            "status": "active",
            "description": "适用于社区图文和评论场景。",
            "created_at": now,
            "updated_at": now,
        }
        self.policy_code_index["pol_default_cn"] = policy_id
        self.policy_versions[policy_version_id] = {
            "policy_version_id": policy_version_id,
            "policy_id": policy_id,
            "version_no": 1,
            "status": "published",
            "scenario_scope": [Scenario.TEA_DRINK.value, Scenario.FOOD_THERAPY.value],
            "content_type_scope": ["note", "comment", "product_detail"],
            "fallback_mode": "review_first",
            "low_confidence_decision": Decision.REVIEW.value,
            "config": {"review_threshold": 0.65, "block_threshold": 0.90},
            "rule_overrides": [
                {
                    "rule_code": "R003",
                    "enabled": True,
                    "override_decision": Decision.BLOCK.value,
                    "override_risk_level": RiskLevel.HIGH.value,
                }
            ],
            "published_by": admin_id,
            "published_at": now,
            "created_at": now,
            "updated_at": now,
        }

        ontology_seed = {
            "mat_001": {
                "entity_id": "mat_001",
                "label": "Material",
                "standard_name": "附子",
                "aliases": ["黑附片"],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {
                    "material_type": "herb",
                    "risk_level": "high",
                    "food_allowed": False,
                },
            },
            "mat_002": {
                "entity_id": "mat_002",
                "label": "Material",
                "standard_name": "甘草",
                "aliases": [],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {
                    "material_type": "herb",
                    "risk_level": "medium",
                    "food_allowed": True,
                },
            },
            "mat_003": {
                "entity_id": "mat_003",
                "label": "Material",
                "standard_name": "海藻",
                "aliases": [],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {
                    "material_type": "herb",
                    "risk_level": "medium",
                    "food_allowed": False,
                },
            },
            "eff_001": {
                "entity_id": "eff_001",
                "label": "Effect",
                "standard_name": "降低血糖/糖尿病相关功效",
                "aliases": ["降血糖"],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {"effect_type": "effect_claim", "risk_level": "high"},
            },
            "pop_001": {
                "entity_id": "pop_001",
                "label": "Population",
                "standard_name": "孕妇",
                "aliases": [],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {"population_type": "pregnant"},
            },
            "ctx_001": {
                "entity_id": "ctx_001",
                "label": "Context",
                "standard_name": "tea_drink",
                "aliases": ["代茶饮"],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {"context_name": "tea_drink"},
            },
        }
        self.ontology_entities.update(ontology_seed)

        self.knowledge_cards["mat_001"] = {
            "entity": {
                "entity_id": "mat_001",
                "standard_name": "附子",
                "label": "Material",
                "risk_level": "high",
            },
            "aliases": ["黑附片"],
            "effects": ["温补相关传统功效"],
            "not_for_populations": ["pregnant"],
            "allowed_contexts": [],
            "prohibited_contexts": ["tea_drink", "food_therapy"],
            "contraindications": [
                {
                    "target_entity_id": "mat_003",
                    "target_name": "海藻",
                    "relation": "CONTRAINDICATED_WITH",
                }
            ],
            "kb_version": "kb-2026-05-29-01",
        }
        self.knowledge_cards["mat_002"] = {
            "entity": {
                "entity_id": "mat_002",
                "standard_name": "甘草",
                "label": "Material",
                "risk_level": "medium",
            },
            "aliases": [],
            "effects": ["补气"],
            "not_for_populations": [],
            "allowed_contexts": ["food_therapy"],
            "prohibited_contexts": [],
            "contraindications": [
                {
                    "target_entity_id": "mat_003",
                    "target_name": "海藻",
                    "relation": "CONTRAINDICATED_WITH",
                }
            ],
            "kb_version": "kb-2026-05-29-01",
        }

        sample_result_id = uuid4()
        sample_request_id = uuid4()
        self.requests[sample_request_id] = {
            "request_id": sample_request_id,
            "tenant_id": tenant_id,
            "client_id": client_id,
            "batch_id": None,
            "policy_version_id": policy_version_id,
            "trace_id": "trc_seed_review_task",
            "content_id": "seed_content_001",
            "request_mode": "sync",
            "content_type": "note",
            "scenario": "tea_drink",
            "content_text": "甘草和海藻一起泡茶，孕妇也能长期喝吗？",
            "content_text_hash": "seed-hash",
            "metadata_json": {"source": "seed"},
            "idempotency_key": None,
            "created_at": now - timedelta(hours=1),
            "updated_at": now - timedelta(hours=1),
        }
        self.results[sample_result_id] = {
            "result_id": sample_result_id,
            "request_id": sample_request_id,
            "tenant_id": tenant_id,
            "trace_id": "trc_seed_review_task",
            "content_id": "seed_content_001",
            "content_text": "甘草和海藻一起泡茶，孕妇也能长期喝吗？",
            "content_type": "note",
            "scenario": "tea_drink",
            "kb_version_id": kb_version_id,
            "policy_version_id": policy_version_id,
            "decision": Decision.REVIEW.value,
            "risk_level": RiskLevel.HIGH.value,
            "confidence": 0.88,
            "recommended_action": "expert_review",
            "fallback_triggered": False,
            "fallback_reason": None,
            "prompt_version": "prompt-v1",
            "model_version": "demo-model-v1",
            "latency_ms": 320,
            "explanation": "内容同时出现配伍禁忌关系与特殊人群长期服用风险，建议人工复核。",
            "hit_rules": [
                {
                    "rule_id": "R002",
                    "rule_name": "配伍禁忌校验",
                    "rule_version": "1.0.0",
                    "risk_level": "High",
                    "decision": "Review",
                    "reason": "甘草与海藻存在配伍禁忌关系。",
                },
                {
                    "rule_id": "R004",
                    "rule_name": "特殊人群长期服用风险",
                    "rule_version": "1.0.0",
                    "risk_level": "Medium",
                    "decision": "Review",
                    "reason": "涉及孕妇与长期服用表述。",
                },
            ],
            "entities": [
                {
                    "text": "甘草",
                    "standard_name": "甘草",
                    "type": "material",
                    "start": 0,
                    "end": 2,
                    "confidence": 0.98,
                    "entity_id": "mat_002",
                },
                {
                    "text": "海藻",
                    "standard_name": "海藻",
                    "type": "material",
                    "start": 3,
                    "end": 5,
                    "confidence": 0.98,
                    "entity_id": "mat_003",
                },
            ],
            "evidence_spans": [
                {
                    "text": "甘草和海藻一起泡茶",
                    "start": 0,
                    "end": 9,
                    "rule_id": "R002",
                    "entity_id": None,
                    "evidence_type": "raw_text",
                }
            ],
            "ontology_facts": [
                {
                    "subject": "甘草",
                    "relation": "CONTRAINDICATED_WITH",
                    "object": "海藻",
                    "kb_version": "kb-2026-05-29-01",
                }
            ],
            "created_at": now - timedelta(hours=1),
            "updated_at": now - timedelta(hours=1),
        }
        self.result_by_request_id[sample_request_id] = sample_result_id

        task_id = uuid4()
        self.review_tasks[task_id] = {
            "task_id": task_id,
            "result_id": sample_result_id,
            "tenant_id": tenant_id,
            "assignee_user_id": reviewer_id,
            "status": ReviewTaskStatus.PENDING.value,
            "queue_name": "default",
            "sla_due_at": now + timedelta(hours=4),
            "final_decision": None,
            "final_action": None,
            "overwrite_system_decision": False,
            "resolution_reason": None,
            "resolution_note": None,
            "claimed_at": None,
            "completed_at": None,
            "created_at": now - timedelta(hours=1),
            "updated_at": now - timedelta(hours=1),
        }
        self.review_task_by_result_id[sample_result_id] = task_id

        feedback_id = uuid4()
        self.feedbacks[feedback_id] = {
            "feedback_id": feedback_id,
            "task_id": task_id,
            "result_id": sample_result_id,
            "tenant_id": tenant_id,
            "feedback_type": FeedbackType.EXPLANATION_UNCLEAR.value,
            "target_rule_id": None,
            "target_entity_ref_id": None,
            "comment": "可增加知识来源说明。",
            "labels": {"needs_rule_tuning": False},
            "created_by": reviewer_id,
            "created_at": now - timedelta(minutes=30),
        }
