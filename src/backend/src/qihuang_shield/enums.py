from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Compatibility helper for string enums."""


class Decision(StrEnum):
    PASS = "pass"
    REVIEW = "review"
    BLOCK = "block"


class DecisionDisplay(StrEnum):
    PASS = "Pass"
    REVIEW = "Review"
    BLOCK = "Block"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskLevelDisplay(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class BatchStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    PARTIAL_SUCCESS = "partial_success"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class KBVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    ROLLED_BACK = "rolled_back"


class RuleVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class PolicyVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class RuleType(StrEnum):
    MATERIAL_IDENTITY = "material_identity"
    CONTRAINDICATION = "contraindication"
    EFFECT_CLAIM = "effect_claim"
    POPULATION_RISK = "population_risk"
    ADVERSARIAL_EXPRESSION = "adversarial_expression"
    OTHER = "other"


class ContentType(StrEnum):
    NOTE = "note"
    COMMENT = "comment"
    PRODUCT_DETAIL = "product_detail"
    TRANSCRIPT = "transcript"
    OTHER = "other"


class Scenario(StrEnum):
    FOOD_THERAPY = "food_therapy"
    TEA_DRINK = "tea_drink"
    WEIGHT_LOSS = "weight_loss"
    GENERAL_HEALTH = "general_health"
    OTHER = "other"


class RecommendedAction(StrEnum):
    ALLOW = "allow"
    REJECT = "reject"
    MODIFY_REQUIRED = "modify_required"
    EXPERT_REVIEW = "expert_review"
    MANUAL_CONFIRM_BLOCK = "manual_confirm_block"
    BLOCK_OR_MANUAL_CONFIRM = "block_or_manual_confirm"


class RoleCode(StrEnum):
    REVIEWER = "reviewer"
    EXPERT = "expert"
    OPERATOR = "operator"
    ONTOLOGY_ADMIN = "ontology_admin"
    AUDITOR = "auditor"
    ADMIN = "admin"


class EntityLabel(StrEnum):
    MATERIAL = "Material"
    HERB = "Herb"
    FORMULA = "Formula"
    ALIAS = "Alias"
    DISEASE = "Disease"
    SYMPTOM = "Symptom"
    EFFECT = "Effect"
    PATTERN = "Pattern"
    PATHOGENESIS = "Pathogenesis"
    TREATMENT_METHOD = "TreatmentMethod"
    TREATMENT_PRINCIPLE = "TreatmentPrinciple"
    USAGE_METHOD = "UsageMethod"
    POPULATION = "Population"
    CONTEXT = "Context"
    RULE_ANCHOR = "RuleAnchor"
    KB_VERSION = "KBVersion"


class EvidenceType(StrEnum):
    RAW_TEXT = "raw_text"
    ENTITY = "entity"
    GRAPH_FACT = "graph_fact"
    RULE_EXPLANATION = "rule_explanation"
