from __future__ import annotations

from ..schemas import OntologyValidationIssueView, OntologyValidationReportView
from .relation_schema import canonical_relation_code
from ..store import InMemoryStore


ALLOWED_ONTOLOGY_TYPES = {
    "Concept", "Material", "Disease", "Symptom", "Pattern", "Pathogenesis",
    "TreatmentPrinciple", "TreatmentMethod", "Formula", "Herb", "Effect",
    "Population", "Context", "Scenario", "UsageMethod", "Property", "NatureFlavor",
    "ZangFu", "Meridian", "MeridianSystem", "Acupoint", "Constitution", "Season", "Stage",
    "Dose", "FormulaRole", "Other",
}


class OntologyBaseValidator:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def validate(self) -> OntologyValidationReportView:
        issues: list[OntologyValidationIssueView] = []
        issues.extend(self._validate_concepts())
        issues.extend(self._validate_versions())
        issues.extend(self._validate_relation_definitions())
        issues.extend(self._validate_aliases())
        issues.extend(self._validate_normalization_decisions())
        issues.extend(self._validate_assertions())
        issues.extend(self._validate_condition_sets())
        issues.extend(self._validate_evidence_sources())
        issues.extend(self._validate_evidence_links())
        issues.extend(self._validate_change_records())
        status = "ok" if not issues else "warning"
        return OntologyValidationReportView(status=status, issue_count=len(issues), issues=issues)


    def _validate_concepts(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for concept_id, concept in self.store.ontology_entities.items():
            if str(concept.get("label") or "") not in ALLOWED_ONTOLOGY_TYPES:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="unknown_concept_type",
                    message="Concept label is not in the allowed ontology type set",
                    object_type="concept",
                    object_id=concept_id,
                ))
            kb_version = concept.get("kb_version")
            if kb_version and str(kb_version) not in self.store.ontology_versions and not str(kb_version).startswith("kb-"):
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="unknown_concept_version",
                    message="Concept references an unknown ontology version",
                    object_type="concept",
                    object_id=concept_id,
                ))
        return issues

    def _validate_versions(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        allowed_types = {"ontology_schema", "terminology_resource", "knowledge_content"}
        for version_id, version in self.store.ontology_versions.items():
            if str(version.get("version_type") or "") not in allowed_types:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="invalid_version_type",
                    message="Ontology version has an invalid version_type",
                    object_type="ontology_version",
                    object_id=version_id,
                ))
            base = version.get("based_on_version")
            if base and str(base) not in self.store.ontology_versions:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_based_on_version",
                    message="Ontology version references a missing base version",
                    object_type="ontology_version",
                    object_id=version_id,
                ))
        return issues

    def _validate_aliases(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for alias_id, alias in self.store.concept_aliases.items():
            concept_id = alias.get("concept_entity_id") or alias.get("concept_id")
            if concept_id and str(concept_id) not in self.store.ontology_entities:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="alias_unknown_concept",
                    message="Alias references a missing concept",
                    object_type="concept_alias",
                    object_id=alias_id,
                ))
        return issues

    def _validate_normalization_decisions(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for decision_id, decision in self.store.normalization_decisions.items():
            mention_id = decision.get("mention_id")
            if mention_id and str(mention_id) not in self.store.mentions:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="decision_missing_mention",
                    message="Normalization decision references a missing mention",
                    object_type="normalization_decision",
                    object_id=decision_id,
                ))
            chosen_concept_id = decision.get("resolved_concept_id") or decision.get("chosen_concept_id")
            if chosen_concept_id and str(chosen_concept_id) not in self.store.ontology_entities:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="decision_unknown_concept",
                    message="Normalization decision references a missing chosen concept",
                    object_type="normalization_decision",
                    object_id=decision_id,
                ))
        return issues

    def _validate_evidence_sources(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for evidence_id, evidence in self.store.evidence_sources.items():
            document_id = evidence.get("document_id")
            kb_version = evidence.get("kb_version")
            quoted_text = evidence.get("source_text") or evidence.get("quoted_text")
            if document_id and str(document_id) not in self.store.guideline_documents:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="evidence_missing_document",
                    message="Evidence source references a missing document",
                    object_type="evidence_source",
                    object_id=evidence_id,
                ))
            if kb_version and str(kb_version) not in self.store.ontology_versions and not str(kb_version).startswith("kb-"):
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="unknown_evidence_version",
                    message="Evidence source references an unknown ontology version",
                    object_type="evidence_source",
                    object_id=evidence_id,
                ))
            if not quoted_text:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_evidence_text",
                    message="Evidence source has empty quoted/source text",
                    object_type="evidence_source",
                    object_id=evidence_id,
                ))
        return issues

    def _validate_change_records(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for change_id, change in self.store.change_records.items():
            to_version = change.get("to_version")
            from_version = change.get("from_version")
            if to_version and str(to_version) not in self.store.ontology_versions:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="change_unknown_to_version",
                    message="Change record references a missing to_version",
                    object_type="change_record",
                    object_id=change_id,
                ))
            if from_version and str(from_version) not in self.store.ontology_versions:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="change_unknown_from_version",
                    message="Change record references a missing from_version",
                    object_type="change_record",
                    object_id=change_id,
                ))
        return issues

    def _validate_relation_definitions(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for relation_code, relation in self._relation_records().items():
            if not relation.get("domain"):
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_domain",
                    message="Relation definition domain is empty",
                    object_type="relation_definition",
                    object_id=relation_code,
                ))
            if not relation.get("range"):
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_range",
                    message="Relation definition range is empty",
                    object_type="relation_definition",
                    object_id=relation_code,
                ))
            for label in relation.get("domain") or []:
                if str(label) not in ALLOWED_ONTOLOGY_TYPES:
                    issues.append(OntologyValidationIssueView(
                        severity="warning",
                        code="invalid_domain_label",
                        message="Relation definition contains an invalid domain label",
                        object_type="relation_definition",
                        object_id=relation_code,
                    ))
            for label in relation.get("range") or []:
                if str(label) not in ALLOWED_ONTOLOGY_TYPES:
                    issues.append(OntologyValidationIssueView(
                        severity="warning",
                        code="invalid_range_label",
                        message="Relation definition contains an invalid range label",
                        object_type="relation_definition",
                        object_id=relation_code,
                    ))
            schema_version = relation.get("schema_version")
            if schema_version and str(schema_version) not in self.store.ontology_versions and not str(schema_version).startswith("ontology-"):
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="unknown_relation_schema_version",
                    message="Relation definition references an unknown schema version",
                    object_type="relation_definition",
                    object_id=relation_code,
                ))
            inverse_relation = relation.get("inverse_relation")
            if inverse_relation and str(inverse_relation) not in self.store.relation_definitions:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_inverse_relation",
                    message="Relation definition references a missing inverse relation",
                    object_type="relation_definition",
                    object_id=relation_code,
                ))
        return issues

    def _validate_assertions(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for assertion_id, assertion in self.store.ontology_assertions.items():
            relation_code = canonical_relation_code(str(assertion.get("predicate_type") or ""))
            relation = self._relation_record(relation_code)
            subject_id = str(assertion.get("subject_entity_id") or "")
            object_id = assertion.get("object_entity_id")
            object_value = assertion.get("object_value")
            kb_version = assertion.get("kb_version")
            document_id = assertion.get("document_id")
            subject = self.store.ontology_entities.get(subject_id)
            obj = self.store.ontology_entities.get(str(object_id)) if object_id else None
            if kb_version and str(kb_version) not in self.store.ontology_versions and not str(kb_version).startswith("kb-"):
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="unknown_assertion_version",
                    message="Assertion references an unknown ontology version",
                    object_type="assertion",
                    object_id=assertion_id,
                ))
            if document_id and str(document_id) not in self.store.guideline_documents:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_assertion_document",
                    message="Assertion references a missing source document",
                    object_type="assertion",
                    object_id=assertion_id,
                ))
            for evidence_id in assertion.get("evidence_ids") or []:
                if str(evidence_id) not in self.store.evidence_sources:
                    issues.append(OntologyValidationIssueView(
                        severity="warning",
                        code="missing_assertion_evidence",
                        message="Assertion references a missing evidence source",
                        object_type="assertion",
                        object_id=assertion_id,
                    ))
            if relation is None:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="unknown_relation_definition",
                    message="Assertion predicate has no registered relation definition",
                    object_type="assertion",
                    object_id=assertion_id,
                    ))
                continue
            if subject is None:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_subject_concept",
                    message="Assertion subject concept does not exist",
                    object_type="assertion",
                    object_id=assertion_id,
                ))
            else:
                if str(subject.get("label")) not in list(relation.get("domain") or []):
                    issues.append(OntologyValidationIssueView(
                        severity="warning",
                        code="domain_mismatch",
                        message="Assertion subject label is not allowed by relation domain",
                        object_type="assertion",
                        object_id=assertion_id,
                    ))
            if object_id and object_value is None:
                pass
            if object_id and object_value is not None:
                # allowed for current compatibility mode, no issue emitted
                pass
            if object_id:
                if obj is None:
                    issues.append(OntologyValidationIssueView(
                        severity="warning",
                        code="missing_object_concept",
                        message="Assertion object concept does not exist",
                        object_type="assertion",
                        object_id=assertion_id,
                    ))
                else:
                    if str(obj.get("label")) not in list(relation.get("range") or []):
                        issues.append(OntologyValidationIssueView(
                            severity="warning",
                            code="range_mismatch",
                            message="Assertion object label is not allowed by relation range",
                            object_type="assertion",
                            object_id=assertion_id,
                        ))
            elif not object_value:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_object",
                    message="Assertion has neither object_entity_id nor object_value",
                    object_type="assertion",
                    object_id=assertion_id,
                ))
            condition_set_id = assertion.get("condition_set_id")
            if condition_set_id and condition_set_id not in self.store.condition_sets:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_condition_set",
                    message="Assertion references a missing condition set",
                    object_type="assertion",
                    object_id=assertion_id,
                ))
        return issues

    def _relation_records(self) -> dict[str, dict]:
        records: dict[str, dict] = {}
        for relation_code, relation in self.store.relation_definitions.items():
            code = canonical_relation_code(str(relation.get("relation_code") or relation_code))
            records[code] = {
                **relation,
                "relation_code": code,
                "domain": list(relation.get("domain") or []),
                "range": list(relation.get("range") or []),
            }
        for relation_code, relation in getattr(self.store, "relation_schemas", {}).items():
            code = canonical_relation_code(str(relation.get("relation_code") or relation_code))
            records[code] = {
                **records.get(code, {}),
                "relation_code": code,
                "domain": list(relation.get("subject_labels") or []),
                "range": list(relation.get("object_labels") or []),
                "schema_version": relation.get("schema_version"),
                "status": relation.get("status", "published"),
                "inverse_relation": records.get(code, {}).get("inverse_relation"),
            }
        return records

    def _relation_record(self, relation_code: str) -> dict | None:
        record = self._relation_records().get(canonical_relation_code(relation_code))
        if record is None or record.get("status") != "published":
            return None
        return record

    def _validate_condition_sets(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for condition_set_id, condition_set in self.store.condition_sets.items():
            logic = condition_set.get("logic") or {}
            for key in ("all", "any", "not"):
                for item in logic.get(key, []) or []:
                    concept_id = item.get("normalized_concept_id")
                    if concept_id and concept_id not in self.store.ontology_entities:
                        issues.append(OntologyValidationIssueView(
                            severity="warning",
                            code="condition_unknown_concept",
                            message="Condition references an unknown normalized concept",
                            object_type="condition_set",
                            object_id=condition_set_id,
                        ))
        return issues

    def _validate_evidence_links(self) -> list[OntologyValidationIssueView]:
        issues: list[OntologyValidationIssueView] = []
        for link_id, link in self.store.evidence_links.items():
            evidence_id = str(link.get("evidence_id") or "")
            if evidence_id not in self.store.evidence_sources:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_evidence_source",
                    message="Evidence link references missing evidence source",
                    object_type="evidence_link",
                    object_id=link_id,
                ))
            target_type = str(link.get("target_type") or "")
            target_id = str(link.get("target_id") or "")
            if target_type == "assertion" and target_id not in self.store.ontology_assertions:
                issues.append(OntologyValidationIssueView(
                    severity="warning",
                    code="missing_assertion_target",
                    message="Evidence link target assertion does not exist",
                    object_type="evidence_link",
                    object_id=link_id,
                ))
        return issues
