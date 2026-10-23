from __future__ import annotations

from ..exceptions import APIError
from ..schemas import (
    AssertionBundleView,
    ChangeRecordView,
    ConceptBundleView,
    ConceptSearchResultView,
    ConceptVerificationView,
    ConditionSetView,
    EvidenceLinkView,
    EvidenceSourceView,
    KnowledgeReleaseView,
    OntologyAssertionView,
    OntologyEntityView,
    OntologyVersionView,
    ObjectTimelineView,
    ReleaseDiffSectionView,
    ReleaseDiffView,
    RelationDefinitionView,
)
from ..store import InMemoryStore


class OntologyBaseService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def list_concepts(self, *, concept_type: str | None = None, kb_version: str | None = None) -> list[OntologyEntityView]:
        items = list(self.store.ontology_entities.values())
        if concept_type:
            items = [item for item in items if str(item.get("label")) == concept_type]
        if kb_version:
            items = [item for item in items if str(item.get("kb_version")) == kb_version]
        items.sort(key=lambda item: (str(item.get("label") or ""), str(item.get("standard_name") or "")))
        return [OntologyEntityView(**item) for item in items]

    def get_concept(self, concept_id: str) -> OntologyEntityView:
        item = self.store.ontology_entities.get(concept_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Concept not found")
        return OntologyEntityView(**item)

    def search_concepts(
        self,
        *,
        query: str,
        concept_type: str | None = None,
        kb_version: str | None = None,
        limit: int = 20,
    ) -> list[ConceptSearchResultView]:
        normalized_query = str(query or "").strip().lower()
        if not normalized_query:
            raise APIError(status_code=400, code="invalid_request", message="query is required")
        results: list[tuple[int, str, str, dict]] = []
        for concept in self.store.ontology_entities.values():
            if concept_type and str(concept.get("label") or "") != concept_type:
                continue
            if kb_version and str(concept.get("kb_version") or "") != kb_version:
                continue
            standard_name = str(concept.get("standard_name") or "")
            aliases = [str(alias) for alias in (concept.get("aliases") or [])]
            candidates = [(standard_name, "standard_name"), *[(alias, "alias") for alias in aliases]]
            for text, match_type in candidates:
                lower_text = text.lower()
                if lower_text == normalized_query:
                    results.append((0, match_type, text, concept))
                    break
                if normalized_query in lower_text:
                    results.append((1, match_type, text, concept))
                    break
        deduped: dict[str, tuple[int, str, str, dict]] = {}
        for score, match_type, matched_text, concept in results:
            concept_id = str(concept.get("entity_id") or "")
            current = deduped.get(concept_id)
            if current is None or score < current[0]:
                deduped[concept_id] = (score, match_type, matched_text, concept)
        ordered = sorted(
            deduped.values(),
            key=lambda item: (
                item[0],
                str(item[3].get("label") or ""),
                str(item[3].get("standard_name") or ""),
            ),
        )[:limit]
        return [
            ConceptSearchResultView(
                concept=OntologyEntityView(**concept),
                matched_text=matched_text,
                match_type=match_type,
                assertion_count=self._assertion_count_for_concept(str(concept.get("entity_id") or "")),
                evidence_count=self._evidence_count_for_concept(str(concept.get("entity_id") or "")),
            )
            for _, match_type, matched_text, concept in ordered
        ]

    def list_assertions(
        self,
        *,
        predicate_type: str | None = None,
        subject_entity_id: str | None = None,
        object_entity_id: str | None = None,
        kb_version: str | None = None,
        condition_context: dict[str, object] | None = None,
    ) -> list[OntologyAssertionView]:
        items = list(self.store.ontology_assertions.values())
        if predicate_type:
            items = [item for item in items if str(item.get("predicate_type")) == predicate_type]
        if subject_entity_id:
            items = [item for item in items if str(item.get("subject_entity_id")) == subject_entity_id]
        if object_entity_id:
            items = [item for item in items if str(item.get("object_entity_id") or "") == object_entity_id]
        if kb_version:
            items = [item for item in items if str(item.get("kb_version")) == kb_version]
        if condition_context is not None:
            items = [item for item in items if self._assertion_matches_condition_context(item, condition_context)]
        items.sort(key=lambda item: (str(item.get("predicate_type") or ""), str(item.get("subject_entity_id") or ""), str(item.get("object_value") or "")))
        return [OntologyAssertionView(**item) for item in items]


    def list_assertions_for_concept(self, concept_id: str) -> list[OntologyAssertionView]:
        if concept_id not in self.store.ontology_entities:
            raise APIError(status_code=404, code="not_found", message="Concept not found")
        items = [
            item for item in self.store.ontology_assertions.values()
            if item.get("subject_entity_id") == concept_id or item.get("object_entity_id") == concept_id
        ]
        items.sort(key=lambda item: (str(item.get("predicate_type") or ""), str(item.get("subject_entity_id") or "")))
        return [OntologyAssertionView(**item) for item in items]

    def list_evidence_for_assertion(self, assertion_id: str) -> list[EvidenceSourceView]:
        item = self.store.ontology_assertions.get(assertion_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Assertion not found")
        evidence_ids = item.get("evidence_ids") or []
        evidence_items = [
            evidence for evidence_id, evidence in self.store.evidence_sources.items()
            if evidence_id in evidence_ids
        ]
        evidence_items.sort(key=lambda evidence: str(evidence.get("evidence_id") or ""))
        return [EvidenceSourceView(**evidence) for evidence in evidence_items]

    def get_condition_for_assertion(self, assertion_id: str) -> ConditionSetView:
        item = self.store.ontology_assertions.get(assertion_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Assertion not found")
        condition_set_id = item.get("condition_set_id")
        if not condition_set_id:
            raise APIError(status_code=404, code="not_found", message="Assertion has no condition set")
        condition = self.store.condition_sets.get(condition_set_id)
        if condition is None:
            raise APIError(status_code=404, code="not_found", message="Condition set not found")
        return ConditionSetView(**condition)


    def get_assertion_bundle(self, assertion_id: str) -> AssertionBundleView:
        assertion = self.get_assertion(assertion_id)
        condition = None
        raw_assertion = self.store.ontology_assertions.get(assertion_id, {})
        condition_set_id = raw_assertion.get("condition_set_id")
        if condition_set_id and condition_set_id in self.store.condition_sets:
            condition = ConditionSetView(**self.store.condition_sets[condition_set_id])
        evidence_sources = self.list_evidence_for_assertion(assertion_id)
        evidence_links = [
            EvidenceLinkView(**item)
            for item in self.store.evidence_links.values()
            if item.get("target_type") == "assertion" and item.get("target_id") == assertion_id
        ]
        change_records = [
            ChangeRecordView(**item)
            for item in self.store.change_records.values()
            if item.get("object_type") == "assertion" and item.get("object_id") == assertion_id
        ]
        return AssertionBundleView(
            assertion=assertion,
            condition=condition,
            evidence_sources=evidence_sources,
            evidence_links=evidence_links,
            change_records=change_records,
        )

    def get_concept_bundle(self, concept_id: str) -> ConceptBundleView:
        concept = self.get_concept(concept_id)
        assertions = self.list_assertions_for_concept(concept_id)
        evidence_id_set: set[str] = set()
        for assertion in assertions:
            raw = self.store.ontology_assertions.get(assertion.assertion_id, {})
            for evidence_id in raw.get("evidence_ids") or []:
                evidence_id_set.add(str(evidence_id))
        evidence_sources = [
            EvidenceSourceView(**item)
            for evidence_id, item in self.store.evidence_sources.items()
            if evidence_id in evidence_id_set
        ]
        return ConceptBundleView(
            concept=concept,
            assertions=assertions,
            evidence_sources=evidence_sources,
        )

    def get_concept_verification(
        self,
        concept_id: str,
        *,
        kb_version: str | None = None,
    ) -> ConceptVerificationView:
        concept = self.get_concept(concept_id)
        if kb_version and concept.kb_version != kb_version:
            raise APIError(status_code=404, code="not_found", message="Concept not found in release")
        assertion_views = self.list_assertions_for_concept(concept_id)
        if kb_version:
            assertion_views = [item for item in assertion_views if item.kb_version == kb_version]
        assertion_bundles = [self.get_assertion_bundle(item.assertion_id) for item in assertion_views]
        evidence_by_id: dict[str, EvidenceSourceView] = {}
        related_ids: set[str] = set()
        for bundle in assertion_bundles:
            assertion = bundle.assertion
            for evidence in bundle.evidence_sources:
                evidence_by_id[evidence.evidence_id] = evidence
            for candidate_id in (assertion.subject_entity_id, assertion.object_entity_id):
                if candidate_id and candidate_id != concept_id:
                    related_ids.add(candidate_id)
        related_concepts = [
            OntologyEntityView(**self.store.ontology_entities[item_id])
            for item_id in sorted(related_ids)
            if item_id in self.store.ontology_entities
        ]
        change_records = [
            ChangeRecordView(**item)
            for item in self.store.change_records.values()
            if str(item.get("object_id") or "") == concept_id
            or str(item.get("object_id") or "") in {item.assertion.assertion_id for item in assertion_bundles}
        ]
        change_records.sort(key=lambda item: (str(item.created_at), item.change_id))
        return ConceptVerificationView(
            concept=concept,
            release_code=concept.kb_version,
            assertions=assertion_bundles,
            evidence_sources=sorted(evidence_by_id.values(), key=lambda item: item.evidence_id),
            change_records=change_records,
            related_concepts=related_concepts,
        )

    def _assertion_count_for_concept(self, concept_id: str) -> int:
        return sum(
            1
            for item in self.store.ontology_assertions.values()
            if item.get("subject_entity_id") == concept_id or item.get("object_entity_id") == concept_id
        )

    def _evidence_count_for_concept(self, concept_id: str) -> int:
        evidence_ids: set[str] = set()
        for item in self.store.ontology_assertions.values():
            if item.get("subject_entity_id") == concept_id or item.get("object_entity_id") == concept_id:
                evidence_ids.update(str(eid) for eid in (item.get("evidence_ids") or []))
        return len(evidence_ids)

    def list_versions(self) -> list[OntologyVersionView]:
        return [OntologyVersionView(**item) for item in self.store.ontology_versions.values()]

    def list_releases(self) -> list[KnowledgeReleaseView]:
        releases = list(self.store.kb_versions.values())
        releases.sort(
            key=lambda item: (
                str(item.get("created_at") or ""),
                str(item.get("version_code") or ""),
            ),
            reverse=True,
        )
        return [self._build_release_view(item) for item in releases]

    def get_release(self, release_id: str) -> KnowledgeReleaseView:
        requested_id = str(release_id)
        item = next(
            (
                version
                for key, version in self.store.kb_versions.items()
                if requested_id in {
                    str(key),
                    str(version.get("kb_version_id") or ""),
                    str(version.get("version_code") or ""),
                }
            ),
            None,
        )
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Knowledge release not found")
        return self._build_release_view(item)

    def get_release_diff(
        self,
        release_id: str,
        *,
        base_release_id: str | None = None,
        limit: int = 50,
    ) -> ReleaseDiffView:
        target = self.get_release(release_id)
        base = self.get_release(base_release_id) if base_release_id else self._previous_release(target.release_code)
        base_code = base.release_code if base else None
        target_code = target.release_code
        sections: dict[str, ReleaseDiffSectionView] = {}
        counts: dict[str, dict[str, int]] = {}
        for section_name, assets, key_fn, summary_fn in (
            ("concepts", self.store.ontology_entities, self._concept_diff_key, self._concept_diff_summary),
            ("assertions", self.store.ontology_assertions, self._assertion_diff_key, self._assertion_diff_summary),
            ("evidence", self.store.evidence_sources, self._evidence_diff_key, self._evidence_diff_summary),
        ):
            base_items = self._release_asset_map(assets, base_code, key_fn) if base_code else {}
            target_items = self._release_asset_map(assets, target_code, key_fn)
            base_keys = set(base_items)
            target_keys = set(target_items)
            added_keys = sorted(target_keys - base_keys)
            removed_keys = sorted(base_keys - target_keys)
            common_keys = sorted(target_keys & base_keys)
            sections[section_name] = ReleaseDiffSectionView(
                added=[summary_fn(target_items[key]) for key in added_keys[:limit]],
                removed=[summary_fn(base_items[key]) for key in removed_keys[:limit]],
                common_count=len(common_keys),
            )
            counts[section_name] = {
                "added": len(added_keys),
                "removed": len(removed_keys),
                "common": len(common_keys),
            }
        return ReleaseDiffView(
            base_release_code=base_code,
            target_release_code=target_code,
            sections=sections,
            counts=counts,
        )

    def get_object_timeline(
        self,
        object_id: str,
        *,
        object_type: str | None = None,
    ) -> ObjectTimelineView:
        records = [
            ChangeRecordView(**item)
            for item in self.store.change_records.values()
            if str(item.get("object_id") or "") == object_id
            and (object_type is None or str(item.get("object_type") or "") == object_type)
        ]
        records.sort(key=lambda item: (str(item.created_at), item.change_id))
        return ObjectTimelineView(object_id=object_id, object_type=object_type, change_records=records)

    def _build_release_view(self, version: dict) -> KnowledgeReleaseView:
        kb_version_id = version.get("kb_version_id")
        if kb_version_id is None:
            raise APIError(status_code=500, code="invalid_state", message="Knowledge release has no version id")
        release_code = str(version.get("version_code") or "")
        staged_assets = self._staged_assets_for_version(kb_version_id, release_code)
        component_counts: dict[str, int] = {}
        for component_name, store_name in self._release_component_sources().items():
            persisted_count = self._count_version_assets(getattr(self.store, store_name, {}), release_code)
            staged_count = self._count_version_assets(staged_assets.get(store_name, {}) or {}, release_code)
            component_counts[component_name] = persisted_count or staged_count

        projection_count = self._count_version_assets(
            getattr(self.store, "knowledge_card_projections", {}),
            release_code,
        )
        timestamps = {
            "created_at": version.get("created_at"),
            "updated_at": version.get("updated_at"),
        }
        return KnowledgeReleaseView(
            release_id=kb_version_id,
            release_code=release_code,
            kb_version_id=kb_version_id,
            status=str(version.get("status") or ""),
            source_type=str(version.get("source_type") or ""),
            timestamps=timestamps,
            published_at=version.get("published_at"),
            validation_report=version.get("validation_report") or {},
            component_counts=component_counts,
            projection_count=projection_count,
        )

    def _previous_release(self, target_release_code: str) -> KnowledgeReleaseView | None:
        target_version = next(
            (item for item in self.store.kb_versions.values() if item.get("version_code") == target_release_code),
            None,
        )
        target_time = str((target_version or {}).get("published_at") or (target_version or {}).get("created_at") or "")
        candidates = [
            item for item in self.store.kb_versions.values()
            if item.get("version_code") != target_release_code
            and str(item.get("status") or "") == "published"
            and str(item.get("published_at") or item.get("created_at") or "") <= target_time
        ]
        candidates.sort(key=lambda item: str(item.get("published_at") or item.get("created_at") or ""), reverse=True)
        return self._build_release_view(candidates[0]) if candidates else None

    @staticmethod
    def _release_asset_map(assets: dict, release_code: str | None, key_fn) -> dict[str, dict]:
        if not release_code:
            return {}
        result: dict[str, dict] = {}
        for item in assets.values():
            if str(item.get("kb_version") or "") == release_code:
                result[key_fn(item)] = item
        return result

    @staticmethod
    def _concept_diff_key(item: dict) -> str:
        return "|".join([str(item.get("label") or ""), str(item.get("standard_name") or "")])

    @staticmethod
    def _assertion_diff_key(item: dict) -> str:
        return "|".join([
            str(item.get("subject_entity_id") or ""),
            str(item.get("predicate_type") or ""),
            str(item.get("object_entity_id") or item.get("object_value") or ""),
        ])

    @staticmethod
    def _evidence_diff_key(item: dict) -> str:
        return str(item.get("source_text") or item.get("evidence_id") or "")

    @staticmethod
    def _concept_diff_summary(item: dict) -> dict[str, object]:
        return {
            "entity_id": item.get("entity_id"),
            "label": item.get("label"),
            "standard_name": item.get("standard_name"),
            "kb_version": item.get("kb_version"),
        }

    @staticmethod
    def _assertion_diff_summary(item: dict) -> dict[str, object]:
        return {
            "assertion_id": item.get("assertion_id"),
            "predicate_type": item.get("predicate_type"),
            "subject_entity_id": item.get("subject_entity_id"),
            "object_entity_id": item.get("object_entity_id"),
            "object_value": item.get("object_value"),
            "kb_version": item.get("kb_version"),
        }

    @staticmethod
    def _evidence_diff_summary(item: dict) -> dict[str, object]:
        return {
            "evidence_id": item.get("evidence_id"),
            "source_title": item.get("source_title"),
            "source_text": item.get("source_text"),
            "kb_version": item.get("kb_version"),
        }

    def _staged_assets_for_version(self, kb_version_id: object, release_code: str) -> dict:
        for job in self.store.import_jobs.values():
            if str(job.get("kb_version_id") or "") not in {str(kb_version_id), release_code}:
                continue
            staged_snapshot = job.get("staged_snapshot")
            if staged_snapshot:
                return staged_snapshot
        return {}

    @staticmethod
    def _release_component_sources() -> dict[str, str]:
        return {
            "concepts": "ontology_entities",
            "assertions": "ontology_assertions",
            "evidence_sources": "evidence_sources",
            "guideline_documents": "guideline_documents",
            "concept_aliases": "concept_aliases",
            "mentions": "mentions",
            "normalization_decisions": "normalization_decisions",
        }

    @staticmethod
    def _count_version_assets(assets: dict, release_code: str) -> int:
        return sum(
            1
            for asset in assets.values()
            if str(asset.get("kb_version") or asset.get("version_code") or "") == release_code
        )

    def get_version(self, version_id: str) -> OntologyVersionView:
        item = self.store.ontology_versions.get(version_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Ontology version not found")
        return OntologyVersionView(**item)

    def list_relation_definitions(self) -> list[RelationDefinitionView]:
        return [RelationDefinitionView(**item) for item in self.store.relation_definitions.values()]

    def get_relation_definition(self, relation_code: str) -> RelationDefinitionView:
        item = self.store.relation_definitions.get(relation_code)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Relation definition not found")
        return RelationDefinitionView(**item)

    def get_condition_set(self, condition_set_id: str) -> ConditionSetView:
        item = self.store.condition_sets.get(condition_set_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Condition set not found")
        return ConditionSetView(**item)

    def get_evidence_link(self, link_id: str) -> EvidenceLinkView:
        item = self.store.evidence_links.get(link_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Evidence link not found")
        return EvidenceLinkView(**item)

    def get_change_record(self, change_id: str) -> ChangeRecordView:
        item = self.store.change_records.get(change_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Change record not found")
        return ChangeRecordView(**item)

    def get_assertion(self, assertion_id: str) -> OntologyAssertionView:
        item = self.store.ontology_assertions.get(assertion_id)
        if item is None:
            raise APIError(status_code=404, code="not_found", message="Assertion not found")
        return OntologyAssertionView(**item)

    def _assertion_matches_condition_context(
        self,
        assertion: dict,
        condition_context: dict[str, object],
    ) -> bool:
        condition_set_id = assertion.get("condition_set_id")
        if not condition_set_id:
            return True
        condition_set = self.store.condition_sets.get(str(condition_set_id))
        if condition_set is None:
            return False
        logic = condition_set.get("logic") or {}
        all_conditions = logic.get("all") or []
        any_conditions = logic.get("any") or []
        not_conditions = logic.get("not") or []
        if any(not self._condition_item_matches(item, condition_context) for item in all_conditions):
            return False
        if any_conditions and not any(self._condition_item_matches(item, condition_context) for item in any_conditions):
            return False
        if any(self._condition_item_matches(item, condition_context) for item in not_conditions):
            return False
        return True

    def _condition_item_matches(self, item: dict, condition_context: dict[str, object]) -> bool:
        condition_type = str(item.get("type") or "")
        expected_values = self._condition_expected_values(item)
        actual_values = self._context_values_for_condition(condition_type, condition_context)
        operator = str(item.get("operator") or "equals")
        if operator == "equals":
            return bool(expected_values & actual_values)
        if operator == "in":
            return bool(expected_values & actual_values)
        if operator in {"gt", "gte", "lt", "lte"}:
            expected_number = self._condition_expected_number(item)
            actual_numbers = self._context_numeric_values(condition_type, condition_context)
            if expected_number is None or not actual_numbers:
                return False
            if operator == "gt":
                return any(value > expected_number for value in actual_numbers)
            if operator == "gte":
                return any(value >= expected_number for value in actual_numbers)
            if operator == "lt":
                return any(value < expected_number for value in actual_numbers)
            if operator == "lte":
                return any(value <= expected_number for value in actual_numbers)
        if operator == "between":
            bounds = self._condition_expected_bounds(item)
            actual_numbers = self._context_numeric_values(condition_type, condition_context)
            if bounds is None or not actual_numbers:
                return False
            lower, upper = bounds
            return any(lower <= value <= upper for value in actual_numbers)
        return False

    def _condition_expected_values(self, item: dict) -> set[str]:
        values: set[str] = set()
        normalized_concept_id = item.get("normalized_concept_id")
        if normalized_concept_id:
            values.add(str(normalized_concept_id))
            concept = self.store.ontology_entities.get(str(normalized_concept_id))
            if concept is not None:
                values.add(str(concept.get("standard_name") or ""))
                values.update(str(alias) for alias in (concept.get("aliases") or []))
        raw_value = item.get("value")
        if isinstance(raw_value, list):
            values.update(str(value) for value in raw_value)
        elif raw_value is not None:
            values.add(str(raw_value))
        return {value for value in values if value}

    def _context_values_for_condition(self, condition_type: str, condition_context: dict[str, object]) -> set[str]:
        values: set[str] = set()
        for key in (condition_type, f"{condition_type}_id", "concept_ids"):
            raw_value = condition_context.get(key)
            if isinstance(raw_value, (list, tuple, set)):
                values.update(str(value) for value in raw_value)
            elif raw_value is not None:
                values.add(str(raw_value))
        return {value for value in values if value}

    def _condition_expected_number(self, item: dict) -> float | None:
        raw_value = item.get("value")
        if raw_value is None:
            raw_value = item.get("threshold")
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return None

    def _condition_expected_bounds(self, item: dict) -> tuple[float, float] | None:
        raw_min = item.get("min")
        raw_max = item.get("max")
        raw_value = item.get("value")
        if (raw_min is None or raw_max is None) and isinstance(raw_value, (list, tuple)) and len(raw_value) == 2:
            raw_min, raw_max = raw_value
        if (raw_min is None or raw_max is None) and isinstance(raw_value, dict):
            raw_min = raw_value.get("min")
            raw_max = raw_value.get("max")
        try:
            lower = float(raw_min)
            upper = float(raw_max)
        except (TypeError, ValueError):
            return None
        return (min(lower, upper), max(lower, upper))

    def _context_numeric_values(self, condition_type: str, condition_context: dict[str, object]) -> list[float]:
        values: list[float] = []
        for key in (condition_type, f"{condition_type}_value", f"{condition_type}_max", f"{condition_type}_min"):
            raw_value = condition_context.get(key)
            raw_values = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
            for item in raw_values:
                try:
                    values.append(float(item))
                except (TypeError, ValueError):
                    continue
        return values
