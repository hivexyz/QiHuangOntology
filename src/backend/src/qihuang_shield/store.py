from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from .enums import (
    Decision,
    RiskLevel,
    RoleCode,
    RuleType,
    Scenario,
)
from .platform_services import hash_password
from .services.relation_schema import default_relation_schema_records
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
        self.ontology_assertions: dict[str, dict[str, Any]] = {}
        self.evidence_sources: dict[str, dict[str, Any]] = {}
        self.concept_aliases: dict[str, dict[str, Any]] = {}
        self.guideline_documents: dict[str, dict[str, Any]] = {}
        self.mentions: dict[str, dict[str, Any]] = {}
        self.normalization_decisions: dict[str, dict[str, Any]] = {}
        self.knowledge_card_projections: dict[str, dict[str, Any]] = {}
        self.ontology_versions: dict[str, dict[str, Any]] = {}
        self.relation_definitions: dict[str, dict[str, Any]] = {}
        self.condition_sets: dict[str, dict[str, Any]] = {}
        self.evidence_links: dict[str, dict[str, Any]] = {}
        self.change_records: dict[str, dict[str, Any]] = {}
        self.relation_schemas: dict[str, dict[str, Any]] = default_relation_schema_records()
        self.mention_normalization_logs: dict[str, dict[str, Any]] = {}
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

    def persist_audit_log(self, _: dict[str, Any]) -> None:
        return None

    def persist_mention_normalization_log(self, _: dict[str, Any]) -> None:
        return None

    def persist_mention(self, _: dict[str, Any]) -> None:
        return None

    def persist_normalization_decision(self, _: dict[str, Any]) -> None:
        return None

    def persist_knowledge_card_projection(self, _: str, __: dict[str, Any]) -> None:
        return None

    def build_neo4j_provenance_rows(self, source_entity_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
        assertion_rows: list[dict[str, Any]] = []
        evidence_rows: list[dict[str, Any]] = []
        document_rows: list[dict[str, Any]] = []
        support_rows: list[dict[str, Any]] = []
        document_link_rows: list[dict[str, Any]] = []
        object_rows: list[dict[str, Any]] = []
        evidence_ids: set[str] = set()
        document_ids: set[str] = set()

        for assertion in self.ontology_assertions.values():
            if source_entity_ids and assertion.get("subject_entity_id") not in source_entity_ids:
                continue
            if assertion.get("status") != "published":
                continue
            assertion_id = str(assertion["assertion_id"])
            assertion_rows.append(
                {
                    "assertion_id": assertion_id,
                    "subject_entity_id": assertion.get("subject_entity_id"),
                    "predicate_type": assertion.get("predicate_type"),
                    "object_entity_id": assertion.get("object_entity_id"),
                    "object_value": assertion.get("object_value"),
                    "kb_version": assertion.get("kb_version"),
                    "status": assertion.get("status"),
                    "document_id": assertion.get("document_id"),
                }
            )
            if assertion.get("object_entity_id"):
                object_rows.append(
                    {
                        "assertion_id": assertion_id,
                        "object_entity_id": assertion.get("object_entity_id"),
                    }
                )
            for evidence_id in assertion.get("evidence_ids") or []:
                evidence_ids.add(str(evidence_id))
                support_rows.append({"assertion_id": assertion_id, "evidence_id": str(evidence_id)})
            if assertion.get("document_id"):
                document_ids.add(str(assertion["document_id"]))
                document_link_rows.append({"assertion_id": assertion_id, "document_id": str(assertion["document_id"])})

        for evidence_id in evidence_ids:
            evidence = self.evidence_sources.get(evidence_id)
            if evidence is None:
                continue
            evidence_rows.append(
                {
                    "evidence_id": evidence["evidence_id"],
                    "kb_version": evidence.get("kb_version"),
                    "source_type": evidence.get("source_type"),
                    "source_uri": evidence.get("source_uri"),
                    "source_title": evidence.get("source_title"),
                    "source_text": evidence.get("source_text"),
                    "entity_id": evidence.get("entity_id"),
                    "status": evidence.get("status"),
                    "document_id": evidence.get("document_id"),
                }
            )
            if evidence.get("document_id"):
                document_ids.add(str(evidence["document_id"]))

        for document_id in document_ids:
            document = self.guideline_documents.get(document_id)
            if document is None:
                continue
            document_rows.append(
                {
                    "document_id": document["document_id"],
                    "kb_version": document.get("kb_version"),
                    "source_uri": document.get("source_uri"),
                    "title": document.get("title"),
                    "source_type": document.get("source_type"),
                    "status": document.get("status"),
                }
            )

        return {
            "assertion_rows": assertion_rows,
            "evidence_rows": evidence_rows,
            "document_rows": document_rows,
            "support_rows": support_rows,
            "document_link_rows": document_link_rows,
            "object_rows": object_rows,
        }

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
            "client_secret_hash": hash_password("demo-secret"),
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
            "password": hash_password("password123"),
            "status": "active",
            "last_login_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.users[reviewer_id] = {
            "user_id": reviewer_id,
            "email": "reviewer@example.com",
            "display_name": "Reviewer User",
            "password": hash_password("password123"),
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

        rules_seed: list[dict[str, Any]] = [
            {
                "code": "R001",
                "name": "药食同源/原料身份校验",
                "rule_type": RuleType.MATERIAL_IDENTITY,
                "description": "高风险药材用于食疗/茶饮场景",
                "default_decision": Decision.BLOCK,
                "risk_level": RiskLevel.HIGH,
                "conditions": {
                    "all": [
                        {"fact": "scenario", "operator": "in", "value": ["tea_drink", "food_therapy", "weight_loss"]},
                        {"fact": "has_prohibited_context", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "高风险药材{standard_name}在{scenario}场景中禁止使用。",
            },
            {
                "code": "R002",
                "name": "配伍禁忌校验",
                "rule_type": RuleType.CONTRAINDICATION,
                "description": "命中配伍禁忌关系",
                "default_decision": Decision.REVIEW,
                "risk_level": RiskLevel.HIGH,
                "conditions": {
                    "all": [
                        {"fact": "has_contraindication_pair", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "{entity_a}与{entity_b}存在配伍禁忌关系。",
            },
            {
                "code": "R003",
                "name": "功效宣称越界",
                "rule_type": RuleType.EFFECT_CLAIM,
                "description": "普通食疗/茶饮内容宣称治疗疾病",
                "default_decision": Decision.BLOCK,
                "risk_level": RiskLevel.HIGH,
                "conditions": {
                    "all": [
                        {"fact": "scenario", "operator": "in", "value": ["tea_drink", "food_therapy", "general_health"]},
                        {"fact": "has_effect_claim", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "普通食疗/茶饮内容宣称疾病治疗功效。",
            },
            {
                "code": "R004",
                "name": "特殊人群长期服用风险",
                "rule_type": RuleType.POPULATION_RISK,
                "description": "特殊人群长期服用风险提示",
                "default_decision": Decision.REVIEW,
                "risk_level": RiskLevel.MEDIUM,
                "conditions": {
                    "all": [
                        {"fact": "has_population_risk", "operator": "equals", "value": True},
                        {"fact": "has_long_term_usage", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "涉及特殊人群与长期服用表述。",
            },
            {
                "code": "R005",
                "name": "疾病宣称越界",
                "rule_type": RuleType.EFFECT_CLAIM,
                "description": "普通食疗/茶饮/保健场景出现疾病指向性宣称",
                "default_decision": Decision.BLOCK,
                "risk_level": RiskLevel.HIGH,
                "conditions": {
                    "all": [
                        {"fact": "scenario", "operator": "in", "value": ["tea_drink", "food_therapy", "general_health"]},
                        {"fact": "has_disease_reference", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "内容在非临床场景中出现疾病相关指向，存在疾病宣称越界风险。",
            },
            {
                "code": "R006",
                "name": "证候调理表述需人工复核",
                "rule_type": RuleType.OTHER,
                "description": "内容涉及证候/证型表达，需要结合上下文审查",
                "default_decision": Decision.REVIEW,
                "risk_level": RiskLevel.MEDIUM,
                "conditions": {
                    "all": [
                        {"fact": "has_pattern_reference", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "内容涉及中医证候/证型语义，建议结合辨证上下文进行人工复核。",
            },
            {
                "code": "R007",
                "name": "治法表述在消费场景需人工复核",
                "rule_type": RuleType.OTHER,
                "description": "内容涉及治法表达，在消费场景中可能形成医疗暗示",
                "default_decision": Decision.REVIEW,
                "risk_level": RiskLevel.MEDIUM,
                "conditions": {
                    "all": [
                        {"fact": "scenario", "operator": "in", "value": ["tea_drink", "food_therapy", "general_health"]},
                        {"fact": "has_treatment_method_claim", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "内容出现中医治法表达，在消费场景中可能构成医疗暗示，建议人工复核。",
            },
            {
                "code": "R008",
                "name": "症状描述与疾病宣称组合风险",
                "rule_type": RuleType.OTHER,
                "description": "同时出现症状和疾病指向，容易形成变相治疗宣称",
                "default_decision": Decision.BLOCK,
                "risk_level": RiskLevel.HIGH,
                "conditions": {
                    "all": [
                        {"fact": "has_symptom_reference", "operator": "equals", "value": True},
                        {"fact": "has_disease_reference", "operator": "equals", "value": True},
                    ]
                },
                "explanation_template": "内容同时涉及症状与疾病指向，易形成变相治疗宣称。",
            },
        ]
        for idx, seed in enumerate(rules_seed, start=1):
            rule_id = uuid4()
            rule_version_id = uuid4()
            self.rules[rule_id] = {
                "rule_id": rule_id,
                "rule_code": seed["code"],
                "rule_name": seed["name"],
                "rule_type": seed["rule_type"].value,
                "status": "active",
                "description": seed["description"],
                "created_at": now,
                "updated_at": now,
            }
            self.rule_code_index[seed["code"]] = rule_id
            self.rule_versions[rule_version_id] = {
                "rule_version_id": rule_version_id,
                "rule_id": rule_id,
                "version_no": "1.0.0",
                "status": "published",
                "priority": 100 - idx,
                "default_decision": seed["default_decision"].value,
                "risk_level": seed["risk_level"].value,
                "conditions": seed["conditions"],
                "action": {
                    "decision": seed["default_decision"].value,
                    "risk_level": seed["risk_level"].value,
                },
                "explanation_template": seed["explanation_template"],
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
                "label": "Herb",
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
                "label": "Herb",
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
                "label": "Herb",
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
                "aliases": ["妊娠", "孕期"],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {"population_type": "pregnant"},
            },
            "ctx_001": {
                "entity_id": "ctx_001",
                "label": "Context",
                "standard_name": "茶饮",
                "aliases": ["代茶饮", "泡茶"],
                "kb_version": "kb-2026-05-29-01",
                "attributes": {"context_name": "tea_drink"},
            },
                "ctx_food_therapy_seed": {
                    "entity_id": "ctx_food_therapy_seed",
                    "label": "Context",
                    "standard_name": "食疗",
                    "aliases": ["药膳", "膳食"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"context_name": "food_therapy"},
                },
        }
        ontology_seed.update(
            {
                "syn_001": {
                    "entity_id": "syn_001",
                    "label": "Pattern",
                    "standard_name": "脾虚",
                    "aliases": ["脾虚证", "脾气虚证"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "脾气虚弱所表现的证候对象"},
                },
                "path_001": {
                    "entity_id": "path_001",
                    "label": "Pathogenesis",
                    "standard_name": "脾失健运",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "脾运化失常之病理机制"},
                },
                "path_qi_deficiency_seed": {
                    "entity_id": "path_qi_deficiency_seed",
                    "label": "Pathogenesis",
                    "standard_name": "脾气不足",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "脾气不足相关病机种子术语"},
                },
                "prin_001": {
                    "entity_id": "prin_001",
                    "label": "TreatmentPrinciple",
                    "standard_name": "补气",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "治疗原则对象"},
                },
                "method_001": {
                    "entity_id": "method_001",
                    "label": "TreatmentMethod",
                    "standard_name": "益气健脾法",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "治疗方法对象"},
                },
                "formula_001": {
                    "entity_id": "formula_001",
                    "label": "Formula",
                    "standard_name": "四君子汤",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "经典方剂对象"},
                },
                "herb_001": {
                    "entity_id": "herb_001",
                    "label": "Herb",
                    "standard_name": "人参",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "单味中药对象"},
                },
                "pattern_yang_deficiency_seed": {
                    "entity_id": "pattern_yang_deficiency_seed",
                    "label": "Pattern",
                    "standard_name": "阳虚证",
                    "aliases": ["阳虚"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "阳气不足相关证候种子术语"},
                },
                "constitution_yang_deficiency_seed": {
                    "entity_id": "constitution_yang_deficiency_seed",
                    "label": "Constitution",
                    "standard_name": "阳虚体质",
                    "aliases": ["阳虚"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "阳虚体质种子术语"},
                },
                "symptom_abdominal_distension_seed": {
                    "entity_id": "symptom_abdominal_distension_seed",
                    "label": "Symptom",
                    "standard_name": "腹胀",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"definition": "腹部胀满症状种子术语"},
                },
                "property_sweet_seed": {
                    "entity_id": "property_sweet_seed",
                    "label": "Property",
                    "standard_name": "甘",
                    "aliases": ["甘味"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"property_category": "flavor"},
                },
                "property_warm_seed": {
                    "entity_id": "property_warm_seed",
                    "label": "Property",
                    "standard_name": "温",
                    "aliases": ["温性"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"property_category": "nature"},
                },
                "meridian_spleen_seed": {
                    "entity_id": "meridian_spleen_seed",
                    "label": "Meridian",
                    "standard_name": "脾经",
                    "aliases": ["脾"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"meridian_type": "spleen"},
                },
                "meridian_lung_seed": {
                    "entity_id": "meridian_lung_seed",
                    "label": "Meridian",
                    "standard_name": "肺经",
                    "aliases": ["肺"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"meridian_type": "lung"},
                },
                "meridian_stomach_seed": {
                    "entity_id": "meridian_stomach_seed",
                    "label": "Meridian",
                    "standard_name": "胃经",
                    "aliases": ["胃"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"meridian_type": "stomach"},
                },
                "constitution_qi_deficiency_seed": {
                    "entity_id": "constitution_qi_deficiency_seed",
                    "label": "Constitution",
                    "standard_name": "气虚体质",
                    "aliases": ["气虚"],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"constitution_type": "qi_deficiency"},
                },
                "season_long_summer_seed": {
                    "entity_id": "season_long_summer_seed",
                    "label": "Season",
                    "standard_name": "长夏",
                    "aliases": [],
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"season_type": "long_summer"},
                },
            }
        )
        for property_type, standard_name, aliases, category in (
            ("wood", "木", ["肝木"], "five_element"),
            ("fire", "火", ["心火"], "five_element"),
            ("earth", "土", ["脾土"], "five_element"),
            ("metal", "金", ["肺金"], "five_element"),
            ("water", "水", ["肾水"], "five_element"),
            ("sweet", "甘", ["甘味"], "flavor"),
            ("warm", "温", ["温性"], "nature"),
        ):
            ontology_seed.setdefault(
                f"property_seed_{property_type}",
                {
                    "entity_id": f"property_seed_{property_type}",
                    "label": "Property",
                    "standard_name": standard_name,
                    "aliases": aliases,
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"property_type": property_type, "property_category": category},
                },
            )
        for meridian_type, standard_name, aliases in (
            ("lung", "肺经", ["肺"]),
            ("large_intestine", "大肠经", ["大肠"]),
            ("stomach", "胃经", ["胃"]),
            ("spleen", "脾经", ["脾"]),
            ("heart", "心经", ["心"]),
            ("small_intestine", "小肠经", ["小肠"]),
            ("bladder", "膀胱经", ["膀胱"]),
            ("kidney", "肾经", ["肾"]),
            ("pericardium", "心包经", ["心包"]),
            ("triple_energizer", "三焦经", ["三焦"]),
            ("gallbladder", "胆经", ["胆"]),
            ("liver", "肝经", ["肝"]),
            ("du", "督脉", []),
            ("ren", "任脉", []),
            ("chong", "冲脉", []),
            ("dai", "带脉", []),
            ("yinwei", "阴维脉", []),
            ("yangwei", "阳维脉", []),
            ("yinqiao", "阴跷脉", []),
            ("yangqiao", "阳跷脉", []),
        ):
            ontology_seed.setdefault(
                f"meridian_seed_{meridian_type}",
                {
                    "entity_id": f"meridian_seed_{meridian_type}",
                    "label": "Meridian",
                    "standard_name": standard_name,
                    "aliases": aliases,
                    "kb_version": "knowledge-content-v0.1",
                    "attributes": {"meridian_type": meridian_type},
                },
            )
        self.ontology_entities.update(ontology_seed)

        self.knowledge_cards["mat_001"] = {
            "entity": {
                "entity_id": "mat_001",
                "standard_name": "附子",
                "label": "Herb",
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
            "assertion_count": 4,
            "evidence_count": 2,
            "derived_from_assertions": True,
        }
        self.knowledge_cards["mat_002"] = {
            "entity": {
                "entity_id": "mat_002",
                "standard_name": "甘草",
                "label": "Herb",
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
            "assertion_count": 2,
            "evidence_count": 1,
            "derived_from_assertions": True,
        }

        self.evidence_sources.update(
            {
                "evidence_seed_base_001": {
                    "evidence_id": "evidence_seed_base_001",
                    "kb_version": "knowledge-content-v0.1",
                    "source_type": "textbook_paragraph",
                    "source_uri": "seed://tcm-base-textbook",
                    "source_title": "TCM Base Textbook",
                    "source_text": "脾虚证多见乏力、纳差、便溏，常因脾失健运所致。",
                    "entity_id": "syn_001",
                    "status": "published",
                    "document_id": "guide_seed_base_001",
                },
                "evidence_seed_base_002": {
                    "evidence_id": "evidence_seed_base_002",
                    "kb_version": "knowledge-content-v0.1",
                    "source_type": "textbook_paragraph",
                    "source_uri": "seed://tcm-base-textbook",
                    "source_title": "TCM Base Textbook",
                    "source_text": "补气之则，可采用益气健脾法，常以四君子汤为代表。",
                    "entity_id": "prin_001",
                    "status": "published",
                    "document_id": "guide_seed_base_001",
                },
                "evidence_seed_base_003": {
                    "evidence_id": "evidence_seed_base_003",
                    "kb_version": "knowledge-content-v0.1",
                    "source_type": "textbook_entry",
                    "source_uri": "seed://tcm-base-textbook",
                    "source_title": "TCM Base Textbook",
                    "source_text": "四君子汤由人参、白术、茯苓、甘草组成。",
                    "entity_id": "formula_001",
                    "status": "published",
                    "document_id": "guide_seed_base_001",
                },
                "evidence_seed_fuzi_001": {
                    "evidence_id": "evidence_seed_fuzi_001",
                    "kb_version": "kb-2026-05-29-01",
                    "source_type": "guideline_clause",
                    "source_uri": "seed://demo-guideline",
                    "source_title": "Demo Guideline",
                    "source_text": "附子禁用于孕妇及代茶饮、食疗场景。",
                    "entity_id": "mat_001",
                    "status": "published",
                    "document_id": "guide_seed_demo_001",
                },
                "evidence_seed_fuzi_002": {
                    "evidence_id": "evidence_seed_fuzi_002",
                    "kb_version": "kb-2026-05-29-01",
                    "source_type": "guideline_clause",
                    "source_uri": "seed://demo-guideline",
                    "source_title": "Demo Guideline",
                    "source_text": "附子不宜与海藻同服。",
                    "entity_id": "mat_001",
                    "status": "published",
                    "document_id": "guide_seed_demo_001",
                },
                "evidence_seed_gancao_001": {
                    "evidence_id": "evidence_seed_gancao_001",
                    "kb_version": "kb-2026-05-29-01",
                    "source_type": "guideline_clause",
                    "source_uri": "seed://demo-guideline",
                    "source_title": "Demo Guideline",
                    "source_text": "甘草适用于食疗场景，但与海藻配伍禁忌。",
                    "entity_id": "mat_002",
                    "status": "published",
                    "document_id": "guide_seed_demo_001",
                },
            }
        )
        self.guideline_documents.update(
            {
                "guide_seed_base_001": {
                    "document_id": "guide_seed_base_001",
                    "kb_version": "knowledge-content-v0.1",
                    "source_uri": "seed://tcm-base-textbook",
                    "title": "TCM Base Textbook",
                    "source_type": "seed",
                    "status": "published",
                },
                "guide_seed_demo_001": {
                    "document_id": "guide_seed_demo_001",
                    "kb_version": "kb-2026-05-29-01",
                    "source_uri": "seed://demo-guideline",
                    "title": "Demo Guideline",
                    "source_type": "seed",
                    "status": "published",
                }
            }
        )
        self.ontology_assertions.update(
            {
                "assert_base_pattern_path": {
                    "assertion_id": "assert_base_pattern_path",
                    "subject_entity_id": "syn_001",
                    "predicate_type": "HAS_PATHOGENESIS",
                    "object_entity_id": "path_001",
                    "object_value": "脾失健运",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_base_001"],
                    "document_id": "guide_seed_base_001",
                    "condition_set_id": "cond_seed_001",
                },
                "assert_base_principle_method": {
                    "assertion_id": "assert_base_principle_method",
                    "subject_entity_id": "prin_001",
                    "predicate_type": "USES_METHOD",
                    "object_entity_id": "method_001",
                    "object_value": "益气健脾法",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_base_002"],
                    "document_id": "guide_seed_base_001",
                },
                "assert_base_method_formula": {
                    "assertion_id": "assert_base_method_formula",
                    "subject_entity_id": "method_001",
                    "predicate_type": "REALIZED_BY_FORMULA",
                    "object_entity_id": "formula_001",
                    "object_value": "四君子汤",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_base_002"],
                    "document_id": "guide_seed_base_001",
                },
                "assert_base_formula_herb": {
                    "assertion_id": "assert_base_formula_herb",
                    "subject_entity_id": "formula_001",
                    "predicate_type": "HAS_INGREDIENT",
                    "object_entity_id": "herb_001",
                    "object_value": "人参",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_base_003"],
                    "document_id": "guide_seed_base_001",
                },
                "assert_seed_fuzi_pop": {
                    "assertion_id": "assert_seed_fuzi_pop",
                    "subject_entity_id": "mat_001",
                    "predicate_type": "NOT_FOR_POPULATION",
                    "object_entity_id": "pop_001",
                    "object_value": "pregnant",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_fuzi_001"],
                    "document_id": "guide_seed_demo_001",
                },
                "assert_seed_fuzi_ctx_tea": {
                    "assertion_id": "assert_seed_fuzi_ctx_tea",
                    "subject_entity_id": "mat_001",
                    "predicate_type": "PROHIBITED_IN_CONTEXT",
                    "object_entity_id": "ctx_001",
                    "object_value": "tea_drink",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_fuzi_001"],
                    "document_id": "guide_seed_demo_001",
                },
                "assert_seed_fuzi_ctx_food": {
                    "assertion_id": "assert_seed_fuzi_ctx_food",
                    "subject_entity_id": "mat_001",
                    "predicate_type": "PROHIBITED_IN_CONTEXT",
                    "object_entity_id": None,
                    "object_value": "food_therapy",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_fuzi_001"],
                    "document_id": "guide_seed_demo_001",
                },
                "assert_seed_fuzi_contra": {
                    "assertion_id": "assert_seed_fuzi_contra",
                    "subject_entity_id": "mat_001",
                    "predicate_type": "CONTRAINDICATED_WITH",
                    "object_entity_id": "mat_003",
                    "object_value": "海藻",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_fuzi_002"],
                    "document_id": "guide_seed_demo_001",
                },
                "assert_seed_gancao_ctx_food": {
                    "assertion_id": "assert_seed_gancao_ctx_food",
                    "subject_entity_id": "mat_002",
                    "predicate_type": "ALLOWED_IN_CONTEXT",
                    "object_entity_id": None,
                    "object_value": "food_therapy",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_gancao_001"],
                    "document_id": "guide_seed_demo_001",
                },
                "assert_seed_gancao_contra": {
                    "assertion_id": "assert_seed_gancao_contra",
                    "subject_entity_id": "mat_002",
                    "predicate_type": "CONTRAINDICATED_WITH",
                    "object_entity_id": "mat_003",
                    "object_value": "海藻",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "evidence_ids": ["evidence_seed_gancao_001"],
                    "document_id": "guide_seed_demo_001",
                },
            }
        )
        self.ontology_versions.update(
            {
                "ontology-schema-v0.1": {
                    "version_id": "ontology-schema-v0.1",
                    "version_type": "ontology_schema",
                    "version_name": "中医本体结构版本 v0.1",
                    "based_on_version": None,
                    "change_summary": "初版结构冻结，定义8大核心类与核心关系",
                    "change_scope": ["class_definition", "relation_definition", "condition_schema"],
                    "created_at": utcnow(),
                    "created_by": "system_seed",
                    "review_status": "published",
                    "reviewed_by": "system_seed",
                    "published_at": utcnow(),
                    "status": "published",
                },
                "terminology-resource-v0.1": {
                    "version_id": "terminology-resource-v0.1",
                    "version_type": "terminology_resource",
                    "version_name": "中医术语资源版本 v0.1",
                    "based_on_version": None,
                    "change_summary": "初版术语别名与归一资源",
                    "change_scope": ["concept_alias", "normalization_decision"],
                    "created_at": utcnow(),
                    "created_by": "system_seed",
                    "review_status": "published",
                    "reviewed_by": "system_seed",
                    "published_at": utcnow(),
                    "status": "published",
                },
                "knowledge-content-v0.1": {
                    "version_id": "knowledge-content-v0.1",
                    "version_type": "knowledge_content",
                    "version_name": "中医知识内容版本 v0.1",
                    "based_on_version": None,
                    "change_summary": "初版黄金样本断言与证据",
                    "change_scope": ["concept", "assertion", "evidence"],
                    "created_at": utcnow(),
                    "created_by": "system_seed",
                    "review_status": "published",
                    "reviewed_by": "system_seed",
                    "published_at": utcnow(),
                    "status": "published",
                },
            }
        )

        self.relation_definitions.update(
            {
                "HAS_PATHOGENESIS": {
                    "relation_code": "HAS_PATHOGENESIS",
                    "display_name_zh": "具有病机",
                    "definition": "表示某病或某证可由某病机对象解释。",
                    "domain": ["Disease", "Pattern"],
                    "range": ["Pathogenesis"],
                    "semantic_direction": "Disease/Pattern -> Pathogenesis",
                    "inverse_relation": None,
                    "boundary_note": "不用于表达治疗方向。",
                    "condition_note": "若病机仅在特定阶段成立，应进入条件集。",
                    "schema_version": "ontology-schema-v0.1",
                    "status": "published",
                },
                "USES_METHOD": {
                    "relation_code": "USES_METHOD",
                    "display_name_zh": "采用治法",
                    "definition": "表示某个治疗原则通过某种具体治疗方法来落实。",
                    "domain": ["TreatmentPrinciple"],
                    "range": ["TreatmentMethod"],
                    "semantic_direction": "TreatmentPrinciple -> TreatmentMethod",
                    "inverse_relation": None,
                    "boundary_note": "仅表示则到法。",
                    "condition_note": "特定条件通过条件集表达。",
                    "schema_version": "ontology-schema-v0.1",
                    "status": "published",
                },
                "REALIZED_BY_FORMULA": {
                    "relation_code": "REALIZED_BY_FORMULA",
                    "display_name_zh": "由方剂实现",
                    "definition": "表示某个治疗方法可以通过某个方剂对象来实现。",
                    "domain": ["TreatmentMethod"],
                    "range": ["Formula"],
                    "semantic_direction": "TreatmentMethod -> Formula",
                    "inverse_relation": None,
                    "boundary_note": "仅表示法到方。",
                    "condition_note": "特定适用条件通过条件集表达。",
                    "schema_version": "ontology-schema-v0.1",
                    "status": "published",
                },
                "HAS_INGREDIENT": {
                    "relation_code": "HAS_INGREDIENT",
                    "display_name_zh": "由药物组成",
                    "definition": "表示某个方剂由某味中药构成。",
                    "domain": ["Formula"],
                    "range": ["Herb"],
                    "semantic_direction": "Formula -> Herb",
                    "inverse_relation": None,
                    "boundary_note": "仅表示组成关系。",
                    "condition_note": None,
                    "schema_version": "ontology-schema-v0.1",
                    "status": "published",
                },
            }
        )

        self.condition_sets.update(
            {
                "cond_seed_001": {
                    "condition_set_id": "cond_seed_001",
                    "logic": {
                        "all": [
                            {
                                "type": "pathogenesis",
                                "operator": "equals",
                                "value": "脾失健运",
                                "value_type": "concept",
                                "normalized_concept_id": "path_001",
                                "scope_note": "限定病机背景",
                                "source_note": "教材原文限定",
                            }
                        ],
                        "not": [
                            {
                                "type": "pattern",
                                "operator": "equals",
                                "value": "热证",
                                "value_type": "literal",
                                "normalized_concept_id": None,
                                "scope_note": "排除条件",
                                "source_note": "黄金样本示意",
                            }
                        ],
                    },
                    "note": "黄金样本条件集",
                }
            }
        )

        self.evidence_links.update(
            {
                "evlink_seed_001": {
                    "link_id": "evlink_seed_001",
                    "target_type": "assertion",
                    "target_id": "assert_base_pattern_path",
                    "evidence_id": "evidence_seed_base_001",
                    "support_role": "supports_main_claim",
                    "support_strength": "direct",
                    "note": "直接支持脾虚证与脾失健运关系",
                }
            }
        )

        self.change_records.update(
            {
                "chg_seed_001": {
                    "change_id": "chg_seed_001",
                    "object_type": "assertion",
                    "object_id": "assert_base_pattern_path",
                    "change_type": "add",
                    "from_version": None,
                    "to_version": "knowledge-content-v0.1",
                    "change_summary": "新增脾虚证与脾失健运黄金样本断言",
                    "reason": "建立最小中医本体基座种子数据",
                    "impact_note": "为后续关系与条件验证提供样本",
                    "created_at": utcnow(),
                    "created_by": "system_seed",
                    "review_status": "approved",
                }
            }
        )

        self.concept_aliases.update(
            {
                "alias_seed_mat_001_1": {
                    "alias_id": "alias_seed_mat_001_1",
                    "alias_text": "黑附片",
                    "concept_entity_id": "mat_001",
                    "canonical_name": "附子",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "alias_type": "material_alias",
                },
                "alias_seed_pop_001_1": {
                    "alias_id": "alias_seed_pop_001_1",
                    "alias_text": "妊娠",
                    "concept_entity_id": "pop_001",
                    "canonical_name": "孕妇",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "alias_type": "population_alias",
                },
                "alias_seed_pop_001_2": {
                    "alias_id": "alias_seed_pop_001_2",
                    "alias_text": "孕期",
                    "concept_entity_id": "pop_001",
                    "canonical_name": "孕妇",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "alias_type": "population_alias",
                },
                "alias_seed_ctx_001_1": {
                    "alias_id": "alias_seed_ctx_001_1",
                    "alias_text": "代茶饮",
                    "concept_entity_id": "ctx_001",
                    "canonical_name": "茶饮",
                    "kb_version": "kb-2026-05-29-01",
                    "status": "published",
                    "alias_type": "context_alias",
                },
                "alias_seed_pattern_yang_001": {
                    "alias_id": "alias_seed_pattern_yang_001",
                    "alias_text": "阳虚",
                    "concept_entity_id": "pattern_yang_deficiency_seed",
                    "canonical_name": "阳虚证",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "alias_type": "terminology_seed_alias",
                },
                "alias_seed_constitution_yang_001": {
                    "alias_id": "alias_seed_constitution_yang_001",
                    "alias_text": "阳虚",
                    "concept_entity_id": "constitution_yang_deficiency_seed",
                    "canonical_name": "阳虚体质",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "alias_type": "terminology_seed_alias",
                },
                "alias_seed_symptom_abdominal_distension_001": {
                    "alias_id": "alias_seed_symptom_abdominal_distension_001",
                    "alias_text": "腹胀",
                    "concept_entity_id": "symptom_abdominal_distension_seed",
                    "canonical_name": "腹胀",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "alias_type": "terminology_seed_alias",
                },
                "alias_seed_path_qi_deficiency_001": {
                    "alias_id": "alias_seed_path_qi_deficiency_001",
                    "alias_text": "脾气不足",
                    "concept_entity_id": "path_qi_deficiency_seed",
                    "canonical_name": "脾气不足",
                    "kb_version": "knowledge-content-v0.1",
                    "status": "published",
                    "alias_type": "terminology_seed_alias",
                },
            }
        )
