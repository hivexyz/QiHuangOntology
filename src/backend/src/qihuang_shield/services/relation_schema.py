from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CURRENT_RELATION_SCHEMA_VERSION = "ontology-relation-schema-v1"


RELATION_ALIASES: dict[str, str] = {
    "CONTRAINDICATED_FOR": "NOT_FOR_POPULATION",
    "DISALLOWED_IN": "PROHIBITED_IN_CONTEXT",
    "APPLICABLE_IN": "ALLOWED_IN_CONTEXT",
    "INCOMPATIBLE_WITH": "CONTRAINDICATED_WITH",
    "IS_A": "SUBCLASS_OF",
    "HAS_SYNDROME": "INDICATED_FOR_PATTERN",
    "TREATS_SYNDROME": "INDICATED_FOR_PATTERN",
    "INDICATED_FOR_PATTERN": "INDICATED_FOR_PATTERN",
    "INDICATED_FOR_SYMPTOM": "INDICATED_FOR_SYMPTOM",
    "INDICATED_FOR_DISEASE": "INDICATED_FOR_DISEASE",
}


def canonical_relation_code(relation_code: str | None) -> str:
    normalized = str(relation_code or "").strip().upper()
    return RELATION_ALIASES.get(normalized, normalized)


@dataclass(frozen=True, slots=True)
class RelationSchema:
    relation_code: str
    schema_version: str
    subject_labels: frozenset[str]
    object_labels: frozenset[str]
    evidence_required: bool = True
    application_relevant: bool = True
    status: str = "published"

    def to_record(self) -> dict[str, Any]:
        return {
            "relation_code": self.relation_code,
            "schema_version": self.schema_version,
            "subject_labels": sorted(self.subject_labels),
            "object_labels": sorted(self.object_labels),
            "evidence_required": self.evidence_required,
            "application_relevant": self.application_relevant,
            "status": self.status,
        }


DEFAULT_RELATION_SCHEMAS: tuple[RelationSchema, ...] = (
    RelationSchema(
        relation_code="HAS_EFFECT",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Material", "Herb", "Formula"}),
        object_labels=frozenset({"Effect"}),
    ),
    RelationSchema(
        relation_code="NOT_FOR_POPULATION",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Material", "Herb", "Formula"}),
        object_labels=frozenset({"Population"}),
    ),
    RelationSchema(
        relation_code="ALLOWED_IN_CONTEXT",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Material", "Herb", "Formula"}),
        object_labels=frozenset({"Context", "Scenario"}),
    ),
    RelationSchema(
        relation_code="PROHIBITED_IN_CONTEXT",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Material", "Herb", "Formula"}),
        object_labels=frozenset({"Context", "Scenario"}),
    ),
    RelationSchema(
        relation_code="CONTRAINDICATED_WITH",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Material", "Herb", "Formula"}),
        object_labels=frozenset({"Material", "Herb", "Formula"}),
    ),
    RelationSchema(
        relation_code="SUBCLASS_OF",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({
            "Concept",
            "Material",
            "Herb",
            "Formula",
            "Effect",
            "Population",
            "Context",
            "Scenario",
            "Pattern",
            "Pathogenesis",
            "TreatmentPrinciple",
            "TreatmentMethod",
            "UsageMethod",
            "Property",
            "ZangFu",
            "Meridian",
            "MeridianSystem",
            "Constitution",
            "Season",
            "Dose",
            "FormulaRole",
            "Disease",
            "Symptom",
            "Pattern",
        }),
        object_labels=frozenset({
            "Concept",
            "Material",
            "Herb",
            "Formula",
            "Effect",
            "Population",
            "Context",
            "Scenario",
            "Pattern",
            "Pathogenesis",
            "TreatmentPrinciple",
            "TreatmentMethod",
            "UsageMethod",
            "Property",
            "ZangFu",
            "Meridian",
            "MeridianSystem",
            "Constitution",
            "Season",
            "Dose",
            "FormulaRole",
            "Disease",
            "Symptom",
            "Pattern",
        }),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="INDICATED_FOR",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "TreatmentMethod", "TreatmentPrinciple"}),
        object_labels=frozenset({"Pathogenesis", "Effect"}),
    ),
    RelationSchema(
        relation_code="INDICATED_FOR_PATTERN",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "TreatmentMethod", "TreatmentPrinciple"}),
        object_labels=frozenset({"Pattern"}),
    ),
    RelationSchema(
        relation_code="INDICATED_FOR_SYMPTOM",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "Acupoint"}),
        object_labels=frozenset({"Symptom"}),
    ),
    RelationSchema(
        relation_code="INDICATED_FOR_DISEASE",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula"}),
        object_labels=frozenset({"Disease"}),
    ),
    RelationSchema(
        relation_code="HAS_SYMPTOM",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Disease", "Pattern"}),
        object_labels=frozenset({"Symptom"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="HAS_PATHOGENESIS",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Disease", "Pattern"}),
        object_labels=frozenset({"Pathogenesis"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="MANIFESTS_AS_SYMPTOM",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Meridian"}),
        object_labels=frozenset({"Symptom"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="ASSOCIATED_WITH_PATTERN",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Disease", "Symptom"}),
        object_labels=frozenset({"Pattern"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="ASSOCIATED_WITH_DISEASE",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Symptom", "Pattern"}),
        object_labels=frozenset({"Disease"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="BASED_ON_PATTERN",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"TreatmentPrinciple", "TreatmentMethod", "Formula"}),
        object_labels=frozenset({"Pathogenesis", "Pattern"}),
    ),
    RelationSchema(
        relation_code="USES_METHOD",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"TreatmentPrinciple", "Formula"}),
        object_labels=frozenset({"TreatmentMethod"}),
    ),
    RelationSchema(
        relation_code="HAS_USAGE_METHOD",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "TreatmentMethod"}),
        object_labels=frozenset({"UsageMethod"}),
    ),
    RelationSchema(
        relation_code="REALIZED_BY_FORMULA",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"TreatmentPrinciple", "TreatmentMethod"}),
        object_labels=frozenset({"Formula"}),
    ),
    RelationSchema(
        relation_code="HAS_INGREDIENT",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Formula"}),
        object_labels=frozenset({"Herb", "Material"}),
    ),
    RelationSchema(
        relation_code="HAS_FORMULA_ROLE",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Material"}),
        object_labels=frozenset({"FormulaRole"}),
    ),
    RelationSchema(
        relation_code="HAS_PROPERTY",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "Pattern", "Pathogenesis"}),
        object_labels=frozenset({"Property"}),
    ),
    RelationSchema(
        relation_code="HAS_NATURE",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula"}),
        object_labels=frozenset({"NatureFlavor"}),
    ),
    RelationSchema(
        relation_code="HAS_FLAVOR",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula"}),
        object_labels=frozenset({"NatureFlavor"}),
    ),
    RelationSchema(
        relation_code="ENTERS_MERIDIAN",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula"}),
        object_labels=frozenset({"Meridian"}),
    ),
    RelationSchema(
        relation_code="ASSOCIATED_WITH_ORGAN",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Meridian"}),
        object_labels=frozenset({"Property"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="ASSOCIATED_WITH_ZANGFU",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Meridian"}),
        object_labels=frozenset({"ZangFu"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="BELONGS_TO_MERIDIAN_SYSTEM",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Meridian"}),
        object_labels=frozenset({"MeridianSystem"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="FLOWS_TO",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Meridian"}),
        object_labels=frozenset({"Meridian"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="LOCATED_ON_MERIDIAN",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Acupoint"}),
        object_labels=frozenset({"Meridian"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="COMBINES_WITH",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Acupoint"}),
        object_labels=frozenset({"Acupoint"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="SUITABLE_FOR_CONSTITUTION",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "TreatmentMethod"}),
        object_labels=frozenset({"Constitution"}),
    ),
    RelationSchema(
        relation_code="SEASONAL_RELEVANCE",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "TreatmentMethod", "Pattern"}),
        object_labels=frozenset({"Season"}),
    ),
    RelationSchema(
        relation_code="SUITABLE_FOR_STAGE",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula", "TreatmentMethod"}),
        object_labels=frozenset({"Stage"}),
    ),
    RelationSchema(
        relation_code="HAS_DOSE",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Herb", "Formula"}),
        object_labels=frozenset({"Dose"}),
    ),
    RelationSchema(
        relation_code="GENERATES",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Property"}),
        object_labels=frozenset({"Property"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="RESTRICTS",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Property"}),
        object_labels=frozenset({"Property"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="OVERACTS",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Property"}),
        object_labels=frozenset({"Property"}),
        application_relevant=False,
    ),
    RelationSchema(
        relation_code="INSULTS",
        schema_version=CURRENT_RELATION_SCHEMA_VERSION,
        subject_labels=frozenset({"Property"}),
        object_labels=frozenset({"Property"}),
        application_relevant=False,
    ),
)


def default_relation_schema_records() -> dict[str, dict[str, Any]]:
    return {schema.relation_code: schema.to_record() for schema in DEFAULT_RELATION_SCHEMAS}


class RelationSchemaRegistry:
    def __init__(self, records: dict[str, dict[str, Any]] | None = None) -> None:
        self._records = records or default_relation_schema_records()

    def get(self, relation_code: str) -> dict[str, Any] | None:
        record = self._records.get(canonical_relation_code(relation_code))
        if record is None or record.get("status") != "published":
            return None
        return record

    def validate(self, relation_code: str, subject_label: str | None, object_label: str | None) -> tuple[bool, list[str]]:
        relation_code = canonical_relation_code(relation_code)
        record = self.get(relation_code)
        if record is None:
            return True, []
        warnings: list[str] = []
        if subject_label not in set(record.get("subject_labels") or []):
            warnings.append("domain")
        if object_label is not None and object_label not in set(record.get("object_labels") or []):
            warnings.append("range")
        return not warnings, warnings
