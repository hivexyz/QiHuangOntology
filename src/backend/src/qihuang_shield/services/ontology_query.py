"""Ontology query service — Neo4j graph query layer with in-memory fallback.

Encapsulates all Cypher queries needed by the runtime knowledge pipeline. When Neo4j is
unavailable or the query times out, falls back to published assertions first and
then to in-memory read-model projections stored in the Store.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..store import InMemoryStore
from .ontology_base import OntologyBaseService

logger = logging.getLogger(__name__)

NEO4J_QUERY_TIMEOUT_SECONDS = 0.2  # 200ms per PRD spec


@dataclass(slots=True)
class EntityResult:
    entity_id: str
    label: str
    standard_name: str
    aliases: list[str] = field(default_factory=list)
    kb_version: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EntityConstraints:
    """Aggregated constraints for a set of entities."""

    # Maps entity_id -> list of prohibited context standard_names
    prohibited_contexts: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of allowed context standard_names
    allowed_contexts: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of population keys
    not_for_populations: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of effect standard_names
    effects: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of syndrome standard_names
    syndromes: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of pattern standard_names
    patterns: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of symptom standard_names
    symptoms: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of disease standard_names
    diseases: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of treatment method standard_names
    treatment_methods: dict[str, list[str]] = field(default_factory=dict)
    # Maps entity_id -> list of usage method standard_names
    usage_methods: dict[str, list[str]] = field(default_factory=dict)
    # List of (entity_a_id, entity_b_id, relation) contraindication pairs
    contraindication_pairs: list[dict[str, str]] = field(default_factory=list)
    # Maps entity_id -> original entity result
    entity_map: dict[str, EntityResult] = field(default_factory=dict)
    # Relation-level provenance, keyed by (subject_entity_id, predicate_type, object_value).
    assertion_sources: dict[tuple[str, str, str], dict[str, Any]] = field(default_factory=dict)


@dataclass(slots=True)
class ContextResult:
    context_code: str
    display_name: str
    entity_id: str


class OntologyQueryService:
    """Query Neo4j for entity attributes, constraints, and relationships.

    When Neo4j is unavailable or the query times out, falls back to published
    assertions first, then to ``knowledge_card_projections`` and legacy
    ``knowledge_cards`` only as read-model compatibility data.
    """

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def query_entities_by_candidates(
        self,
        candidates: list[str],
        *,
        kb_version: str | None = None,
    ) -> list[EntityResult]:
        """Batch-match candidate terms against entity standard names and aliases.

        Returns results ordered by match confidence: exact standard_name matches
        first, then alias matches.
        """
        if not candidates:
            return []
        kb_version = kb_version or self._active_kb_version_code()

        from neo4j import Driver
        driver = self._get_neo4j_driver()
        if driver is None:
            return self._fallback_query_entities(candidates, kb_version=kb_version)

        try:
            return self._neo4j_query_entities(driver, candidates, kb_version=kb_version)
        except Exception as exc:
            logger.warning("Neo4j entity query failed, falling back to snapshot: %s", exc)
            return self._fallback_query_entities(candidates, kb_version=kb_version)

    def query_entity_constraints(
        self,
        entity_ids: list[str],
        *,
        kb_version: str | None = None,
        condition_context: dict[str, object] | None = None,
    ) -> EntityConstraints:
        """Query all constraints (contexts, populations, effects, contraindications)
        for a set of entity IDs."""
        if not entity_ids:
            return EntityConstraints()
        kb_version = kb_version or self._active_kb_version_code()
        if condition_context:
            return self._fallback_query_constraints(
                entity_ids,
                kb_version=kb_version,
                condition_context=condition_context,
            )

        driver = self._get_neo4j_driver()
        if driver is None:
            return self._fallback_query_constraints(
                entity_ids,
                kb_version=kb_version,
                condition_context=condition_context,
            )

        try:
            return self._neo4j_query_constraints(driver, entity_ids, kb_version=kb_version)
        except Exception as exc:
            logger.warning("Neo4j constraint query failed, falling back to snapshot: %s", exc)
            return self._fallback_query_constraints(
                entity_ids,
                kb_version=kb_version,
                condition_context=condition_context,
            )

    def query_context_by_terms(self, terms: list[str], *, kb_version: str | None = None) -> list[ContextResult]:
        """Match terms against Context entity standard names and aliases."""
        if not terms:
            return []
        kb_version = kb_version or self._active_kb_version_code()

        driver = self._get_neo4j_driver()
        if driver is None:
            return self._fallback_query_contexts(terms, kb_version=kb_version)

        try:
            return self._neo4j_query_contexts(driver, terms, kb_version=kb_version)
        except Exception as exc:
            logger.warning("Neo4j context query failed, falling back to snapshot: %s", exc)
            return self._fallback_query_contexts(terms, kb_version=kb_version)

    def query_all_entities(self, *, kb_version: str | None = None) -> list[EntityResult]:
        """Return all entities from the store (for candidate generation)."""
        kb_version = kb_version or self._active_kb_version_code()
        driver = self._get_neo4j_driver()
        if driver is None:
            return self._fallback_all_entities(kb_version=kb_version)

        try:
            return self._neo4j_all_entities(driver, kb_version=kb_version)
        except Exception as exc:
            logger.warning("Neo4j all-entities query failed: %s", exc)
            return self._fallback_all_entities(kb_version=kb_version)

    def query_ancestors(self, entity_ids: list[str], *, kb_version: str | None = None) -> dict[str, list[EntityResult]]:
        """Return SUBCLASS_OF ancestors for each entity in the active KB."""
        kb_version = kb_version or self._active_kb_version_code()
        ancestors: dict[str, list[EntityResult]] = {entity_id: [] for entity_id in entity_ids}
        visited: dict[str, set[str]] = {entity_id: set() for entity_id in entity_ids}
        parent_by_child: dict[str, list[str]] = {}
        for assertion in self._store.ontology_assertions.values():
            if assertion.get("status") != "published":
                continue
            if kb_version and assertion.get("kb_version") != kb_version:
                continue
            if assertion.get("predicate_type") != "SUBCLASS_OF":
                continue
            parent_id = assertion.get("object_entity_id")
            child_id = assertion.get("subject_entity_id")
            if child_id and parent_id:
                parent_by_child.setdefault(str(child_id), []).append(str(parent_id))

        def walk(root_id: str, current_id: str) -> None:
            for parent_id in parent_by_child.get(current_id, []):
                if parent_id in visited[root_id]:
                    continue
                visited[root_id].add(parent_id)
                parent = self._store.ontology_entities.get(parent_id)
                if parent and (not kb_version or parent.get("kb_version") == kb_version):
                    ancestors[root_id].append(self._entity_to_result(parent))
                walk(root_id, parent_id)

        for entity_id in entity_ids:
            walk(entity_id, entity_id)
        return ancestors

    def query_logic_method_formula_paths(
        self,
        *,
        pattern_or_pathogenesis: str | None = None,
        syndrome_or_pathogenesis: str | None = None,
        kb_version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return minimal 理-法-方-药 paths from TCM core assertions."""
        if pattern_or_pathogenesis is None:
            pattern_or_pathogenesis = syndrome_or_pathogenesis
        kb_version = kb_version or self._active_kb_version_code()
        entities = {
            entity_id: entity
            for entity_id, entity in self._store.ontology_entities.items()
            if not kb_version or entity.get("kb_version") == kb_version
        }
        assertions = [
            assertion for assertion in self._store.ontology_assertions.values()
            if assertion.get("status") == "published"
            and (not kb_version or assertion.get("kb_version") == kb_version)
        ]
        by_subject: dict[str, list[dict[str, Any]]] = {}
        for assertion in assertions:
            by_subject.setdefault(str(assertion.get("subject_entity_id")), []).append(assertion)

        target_names = {pattern_or_pathogenesis} if pattern_or_pathogenesis else None
        def assertion_matches_target(assertion: dict[str, Any]) -> bool:
            if not target_names:
                return True
            values = {str(assertion.get("object_value") or "")}
            object_entity = entities.get(str(assertion.get("object_entity_id") or ""))
            if object_entity is not None:
                values.add(str(object_entity.get("standard_name") or ""))
                values.update(str(alias) for alias in (object_entity.get("aliases") or []))
            return bool(values & target_names)

        paths: list[dict[str, Any]] = []
        for principle_id, rels in by_subject.items():
            principle = entities.get(principle_id)
            if not principle or principle.get("label") != "TreatmentPrinciple":
                continue
            pattern_rels = [rel for rel in rels if rel.get("predicate_type") == "BASED_ON_PATTERN"]
            if target_names:
                pattern_rels = [rel for rel in pattern_rels if assertion_matches_target(rel)]
                if not pattern_rels:
                    continue
            method_rels = [rel for rel in rels if rel.get("predicate_type") == "USES_METHOD"]
            formula_rels = [rel for rel in rels if rel.get("predicate_type") == "REALIZED_BY_FORMULA"]
            for pattern_rel in pattern_rels or [None]:
                for method_rel in method_rels or [None]:
                    for formula_rel in formula_rels or [None]:
                        formula_id = str(formula_rel.get("object_entity_id")) if formula_rel else None
                        herbs = self._formula_herb_roles(formula_id, by_subject, entities) if formula_id else []
                        paths.append({
                            "pattern": self._path_node(pattern_rel, entities) if pattern_rel else None,
                            "principle": self._entity_path_node(principle),
                            "method": self._path_node(method_rel, entities) if method_rel else None,
                            "formula": self._path_node(formula_rel, entities) if formula_rel else None,
                            "herbs": herbs,
                        })
        return paths

    def query_disease_symptom_pattern_paths(
        self,
        *,
        disease: str | None = None,
        symptom: str | None = None,
        pattern: str | None = None,
        kb_version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return 病-症-证 graph paths using ontology assertions where available."""
        kb_version = kb_version or self._active_kb_version_code()
        entities = {
            str(entity["entity_id"]): entity
            for entity in self._store.ontology_entities.values()
            if not kb_version or entity.get("kb_version") == kb_version
        }
        diseases = [e for e in entities.values() if e.get("label") == "Disease"]
        symptoms = [e for e in entities.values() if e.get("label") == "Symptom"]
        patterns = [e for e in entities.values() if e.get("label") == "Pattern"]
        if disease:
            diseases = [e for e in diseases if e.get("standard_name") == disease]
        if symptom:
            symptoms = [e for e in symptoms if e.get("standard_name") == symptom]
        if pattern:
            patterns = [e for e in patterns if e.get("standard_name") == pattern]
        assertions = [
            assertion for assertion in self._store.ontology_assertions.values()
            if assertion.get("status") == "published"
            and (not kb_version or assertion.get("kb_version") == kb_version)
        ]
        by_subject: dict[str, list[dict[str, Any]]] = {}
        for assertion in assertions:
            by_subject.setdefault(str(assertion.get("subject_entity_id")), []).append(assertion)

        paths: list[dict[str, Any]] = []
        for disease_entity in diseases or [None]:
            if disease_entity is None:
                continue
            disease_id = str(disease_entity["entity_id"])
            symptom_links = [
                rel for rel in by_subject.get(disease_id, [])
                if rel.get("predicate_type") == "HAS_SYMPTOM"
            ]
            pattern_links = [
                rel for rel in by_subject.get(disease_id, [])
                if rel.get("predicate_type") == "ASSOCIATED_WITH_PATTERN"
            ]
            if symptom:
                symptom_links = [rel for rel in symptom_links if rel.get("object_value") == symptom]
            if pattern:
                pattern_links = [rel for rel in pattern_links if rel.get("object_value") == pattern]
            for symptom_link in symptom_links or [None]:
                for pattern_link in pattern_links or [None]:
                    symptom_entity = entities.get(str(symptom_link.get("object_entity_id"))) if symptom_link else None
                    pattern_entity = entities.get(str(pattern_link.get("object_entity_id"))) if pattern_link else None
                    paths.append({
                        "disease": self._entity_path_node(disease_entity),
                        "symptom": self._entity_path_node(symptom_entity) if symptom_entity else None,
                        "pattern": self._entity_path_node(pattern_entity) if pattern_entity else None,
                    })
        return paths

    # ------------------------------------------------------------------
    # Neo4j query implementations
    # ------------------------------------------------------------------

    def _neo4j_query_entities(self, driver: Any, candidates: list[str], *, kb_version: str | None) -> list[EntityResult]:
        t0 = time.monotonic()
        with driver.session(database=self._neo4j_database()) as session:
            result = session.run(
                """
                UNWIND $candidates AS candidate
                MATCH (e:Entity)
                WHERE e.kb_version = $kb_version
                  AND (e.standard_name = candidate OR candidate IN (e.aliases))
                RETURN DISTINCT e.entity_id AS entity_id,
                       e.label AS label,
                       e.standard_name AS standard_name,
                       e.aliases AS aliases,
                       e.kb_version AS kb_version,
                       e.attributes_json AS attributes_json
                """,
                candidates=candidates,
                kb_version=kb_version,
                timeout=NEO4J_QUERY_TIMEOUT_SECONDS,
            )
            rows = list(result)
        elapsed = (time.monotonic() - t0) * 1000
        logger.debug("Neo4j entity query: %d candidates → %d results in %.1fms", len(candidates), len(rows), elapsed)
        return self._rows_to_entities(rows)

    def _neo4j_query_constraints(self, driver: Any, entity_ids: list[str], *, kb_version: str | None) -> EntityConstraints:
        t0 = time.monotonic()
        with driver.session(database=self._neo4j_database()) as session:
            result = session.run(
                """
                UNWIND $entity_ids AS eid
                MATCH (e:Entity {entity_id: eid, kb_version: $kb_version})
                OPTIONAL MATCH (e)-[rpc:PROHIBITED_IN_CONTEXT {kb_version: $kb_version}]->(pc:Entity {kb_version: $kb_version})
                OPTIONAL MATCH (e)-[rac:ALLOWED_IN_CONTEXT {kb_version: $kb_version}]->(ac:Entity {kb_version: $kb_version})
                OPTIONAL MATCH (e)-[rpop:NOT_FOR_POPULATION {kb_version: $kb_version}]->(pop:Entity {kb_version: $kb_version})
                OPTIONAL MATCH (e)-[reff:HAS_EFFECT {kb_version: $kb_version}]->(eff:Entity {kb_version: $kb_version})
                OPTIONAL MATCH (e)-[r:CONTRAINDICATED_WITH]-(other:Entity)
                WHERE r.kb_version = $kb_version AND other.kb_version = $kb_version AND other.entity_id IN $entity_ids
                RETURN e.entity_id AS entity_id,
                       e.standard_name AS standard_name,
                       e.label AS label,
                       e.aliases AS aliases,
                       e.kb_version AS kb_version,
                       e.attributes_json AS attributes_json,
                       collect(DISTINCT pc.standard_name) AS prohibited,
                       collect(DISTINCT ac.standard_name) AS allowed,
                       collect(DISTINCT pop.attributes_json) AS populations_raw,
                       collect(DISTINCT eff.standard_name) AS effects,
                       collect(DISTINCT {other_id: other.entity_id, other_name: other.standard_name, rel: type(r)}) AS contra
                """,
                entity_ids=entity_ids,
                kb_version=kb_version,
                timeout=NEO4J_QUERY_TIMEOUT_SECONDS,
            )
            rows = list(result)
        elapsed = (time.monotonic() - t0) * 1000
        logger.debug("Neo4j constraint query: %d entities in %.1fms", len(entity_ids), elapsed)

        constraints = EntityConstraints()
        for row in rows:
            eid = row["entity_id"]
            constraints.entity_map[eid] = EntityResult(
                entity_id=eid,
                label=row.get("label") or "Entity",
                standard_name=row.get("standard_name") or "",
                aliases=list(row.get("aliases") or []),
                kb_version=row.get("kb_version") or "",
                attributes=self._parse_json(row.get("attributes_json")),
            )

            prohibited = [v for v in (row.get("prohibited") or []) if v]
            if prohibited:
                constraints.prohibited_contexts[eid] = prohibited

            allowed = [v for v in (row.get("allowed") or []) if v]
            if allowed:
                constraints.allowed_contexts[eid] = allowed

            # Parse population JSON to extract population_type
            pops_raw = row.get("populations_raw") or []
            pop_keys: list[str] = []
            for pop_json in pops_raw:
                if isinstance(pop_json, str):
                    try:
                        import json
                        pop_data = json.loads(pop_json)
                    except (json.JSONDecodeError, TypeError):
                        continue
                elif isinstance(pop_json, dict):
                    pop_data = pop_json
                else:
                    continue
                pop_type = pop_data.get("population_type")
                if pop_type:
                    pop_keys.append(pop_type)
            if pop_keys:
                constraints.not_for_populations[eid] = pop_keys

            effects = [v for v in (row.get("effects") or []) if v]
            if effects:
                constraints.effects[eid] = effects

            for contra in row.get("contra") or []:
                if contra and contra.get("other_id"):
                    pair = {
                        "entity_a": eid,
                        "entity_b": contra["other_id"],
                        "relation": contra.get("rel", "CONTRAINDICATED_WITH"),
                    }
                    # Deduplicate: ensure we don't add the same pair twice
                    existing = {
                        (p["entity_a"], p["entity_b"]) for p in constraints.contraindication_pairs
                    }
                    key = (pair["entity_a"], pair["entity_b"])
                    if key not in existing and (pair["entity_b"], pair["entity_a"]) not in existing:
                        constraints.contraindication_pairs.append(pair)

        self._attach_published_assertion_sources(constraints, entity_ids, kb_version=kb_version)
        return constraints

    def _neo4j_query_contexts(self, driver: Any, terms: list[str], *, kb_version: str | None) -> list[ContextResult]:
        t0 = time.monotonic()
        with driver.session(database=self._neo4j_database()) as session:
            result = session.run(
                """
                UNWIND $terms AS term
                MATCH (e:Entity:Context)
                WHERE e.kb_version = $kb_version
                  AND (e.standard_name = term OR term IN (e.aliases))
                RETURN DISTINCT e.entity_id AS entity_id,
                       e.standard_name AS standard_name,
                       e.attributes_json AS attributes_json
                """,
                terms=terms,
                kb_version=kb_version,
                timeout=NEO4J_QUERY_TIMEOUT_SECONDS,
            )
            rows = list(result)
        elapsed = (time.monotonic() - t0) * 1000
        logger.debug("Neo4j context query: %d terms → %d results in %.1fms", len(terms), len(rows), elapsed)

        results: list[ContextResult] = []
        for row in rows:
            attrs = self._parse_json(row.get("attributes_json"))
            context_code = attrs.get("context_name", row.get("standard_name", ""))
            results.append(ContextResult(
                context_code=context_code,
                display_name=row.get("standard_name", context_code),
                entity_id=row["entity_id"],
            ))
        return results

    def _neo4j_all_entities(self, driver: Any, *, kb_version: str | None) -> list[EntityResult]:
        with driver.session(database=self._neo4j_database()) as session:
            result = session.run(
                """
                MATCH (e:Entity)
                WHERE e.kb_version = $kb_version
                RETURN e.entity_id AS entity_id,
                       e.label AS label,
                       e.standard_name AS standard_name,
                       e.aliases AS aliases,
                       e.kb_version AS kb_version,
                       e.attributes_json AS attributes_json
                """
            , kb_version=kb_version)
            return self._rows_to_entities(list(result))

    # ------------------------------------------------------------------
    # In-memory fallback implementations
    # ------------------------------------------------------------------

    def _fallback_query_entities(self, candidates: list[str], *, kb_version: str | None) -> list[EntityResult]:
        results: list[EntityResult] = []
        seen: set[str] = set()
        candidate_set = set(candidates)

        for entity_id, entity in self._store.ontology_entities.items():
            if kb_version and entity.get("kb_version") != kb_version:
                continue
            standard_name = str(entity.get("standard_name", ""))
            aliases = [str(a) for a in (entity.get("aliases") or [])]

            if standard_name in candidate_set and entity_id not in seen:
                seen.add(entity_id)
                results.append(self._entity_to_result(entity))
                continue

            for alias in aliases:
                if alias in candidate_set and entity_id not in seen:
                    seen.add(entity_id)
                    results.append(self._entity_to_result(entity))
                    break

        return results

    def _fallback_query_constraints(
        self,
        entity_ids: list[str],
        *,
        kb_version: str | None,
        condition_context: dict[str, object] | None = None,
    ) -> EntityConstraints:
        constraints = EntityConstraints()
        entity_id_set = set(entity_ids)

        for eid in entity_ids:
            entity = self._store.ontology_entities.get(eid)
            if entity is not None and (not kb_version or entity.get("kb_version") == kb_version):
                constraints.entity_map[eid] = self._entity_to_result(entity)

        published_version_map = {
            item["version_code"]: item
            for item in self._store.kb_versions.values()
            if item.get("status") == "published"
        }
        used_assertions = False
        ontology_base_service = OntologyBaseService(self._store) if condition_context else None
        for assertion in self._store.ontology_assertions.values():
            if assertion.get("subject_entity_id") not in entity_id_set:
                continue
            if assertion.get("status") != "published":
                continue
            if kb_version and assertion.get("kb_version") != kb_version:
                continue
            if assertion.get("kb_version") not in published_version_map:
                continue
            if ontology_base_service is not None and not ontology_base_service._assertion_matches_condition_context(assertion, condition_context):
                continue
            used_assertions = True
            eid = assertion["subject_entity_id"]
            predicate = assertion.get("predicate_type")
            object_value = str(assertion.get("object_value") or "")
            object_entity_id = assertion.get("object_entity_id")
            if predicate and object_value:
                source = self._build_assertion_source(assertion, published_version_map)
                constraints.assertion_sources[(eid, str(predicate), object_value)] = source

            if predicate == "PROHIBITED_IN_CONTEXT" and object_value:
                constraints.prohibited_contexts.setdefault(eid, []).append(object_value)
            elif predicate == "ALLOWED_IN_CONTEXT" and object_value:
                constraints.allowed_contexts.setdefault(eid, []).append(object_value)
            elif predicate == "NOT_FOR_POPULATION" and object_value:
                constraints.not_for_populations.setdefault(eid, []).append(object_value)
            elif predicate == "HAS_EFFECT" and object_value:
                constraints.effects.setdefault(eid, []).append(object_value)
            elif predicate == "INDICATED_FOR" and object_value:
                constraints.syndromes.setdefault(eid, []).append(object_value)
            elif predicate == "INDICATED_FOR_PATTERN" and object_value:
                constraints.patterns.setdefault(eid, []).append(object_value)
            elif predicate == "INDICATED_FOR_SYMPTOM" and object_value:
                constraints.symptoms.setdefault(eid, []).append(object_value)
            elif predicate == "INDICATED_FOR_DISEASE" and object_value:
                constraints.diseases.setdefault(eid, []).append(object_value)
            elif predicate == "USES_METHOD" and object_value:
                constraints.treatment_methods.setdefault(eid, []).append(object_value)
            elif predicate == "HAS_USAGE_METHOD" and object_value:
                constraints.usage_methods.setdefault(eid, []).append(object_value)
            elif predicate == "CONTRAINDICATED_WITH" and object_entity_id and object_entity_id in entity_id_set:
                pair = {
                    "entity_a": eid,
                    "entity_b": object_entity_id,
                    "relation": "CONTRAINDICATED_WITH",
                }
                existing = {(p["entity_a"], p["entity_b"]) for p in constraints.contraindication_pairs}
                key = (pair["entity_a"], pair["entity_b"])
                if key not in existing and (pair["entity_b"], pair["entity_a"]) not in existing:
                    constraints.contraindication_pairs.append(pair)

        if used_assertions:
            constraints.prohibited_contexts = {
                key: sorted(set(values)) for key, values in constraints.prohibited_contexts.items()
            }
            constraints.allowed_contexts = {
                key: sorted(set(values)) for key, values in constraints.allowed_contexts.items()
            }
            constraints.not_for_populations = {
                key: sorted(set(values)) for key, values in constraints.not_for_populations.items()
            }
            constraints.effects = {
                key: sorted(set(values)) for key, values in constraints.effects.items()
            }
            constraints.syndromes = {
                key: sorted(set(values)) for key, values in constraints.syndromes.items()
            }
            constraints.patterns = {
                key: sorted(set(values)) for key, values in constraints.patterns.items()
            }
            constraints.symptoms = {
                key: sorted(set(values)) for key, values in constraints.symptoms.items()
            }
            constraints.diseases = {
                key: sorted(set(values)) for key, values in constraints.diseases.items()
            }
            constraints.treatment_methods = {
                key: sorted(set(values)) for key, values in constraints.treatment_methods.items()
            }
            constraints.usage_methods = {
                key: sorted(set(values)) for key, values in constraints.usage_methods.items()
            }
            return constraints

        for eid in entity_ids:
            card = self._store.knowledge_card_projections.get(eid)
            if card is None:
                continue
            if kb_version and card.get("kb_version") != kb_version:
                continue

            prohibited = card.get("prohibited_contexts") or []
            if prohibited:
                constraints.prohibited_contexts[eid] = list(prohibited)

            allowed = card.get("allowed_contexts") or []
            if allowed:
                constraints.allowed_contexts[eid] = list(allowed)

            populations = card.get("not_for_populations") or []
            if populations:
                constraints.not_for_populations[eid] = list(populations)

            effects = card.get("effects") or []
            if effects:
                constraints.effects[eid] = list(effects)
            syndromes = card.get("syndromes") or []
            if syndromes:
                constraints.syndromes[eid] = list(syndromes)
            patterns = card.get("patterns") or []
            if patterns:
                constraints.patterns[eid] = list(patterns)
            symptoms = card.get("symptoms") or []
            if symptoms:
                constraints.symptoms[eid] = list(symptoms)
            diseases = card.get("diseases") or []
            if diseases:
                constraints.diseases[eid] = list(diseases)
            methods = card.get("treatment_methods") or []
            if methods:
                constraints.treatment_methods[eid] = list(methods)
            usage_methods = card.get("usage_methods") or []
            if usage_methods:
                constraints.usage_methods[eid] = list(usage_methods)

            for contra in card.get("contraindications") or []:
                target_id = contra.get("target_entity_id")
                if target_id and target_id in entity_id_set:
                    pair = {
                        "entity_a": eid,
                        "entity_b": target_id,
                        "relation": contra.get("relation", "CONTRAINDICATED_WITH"),
                    }
                    existing = {
                        (p["entity_a"], p["entity_b"]) for p in constraints.contraindication_pairs
                    }
                    key = (pair["entity_a"], pair["entity_b"])
                    if key not in existing and (pair["entity_b"], pair["entity_a"]) not in existing:
                        constraints.contraindication_pairs.append(pair)

        return constraints

    def _attach_published_assertion_sources(
        self,
        constraints: EntityConstraints,
        entity_ids: list[str],
        *,
        kb_version: str | None,
    ) -> None:
        entity_id_set = set(entity_ids)
        published_version_map = {
            item["version_code"]: item
            for item in self._store.kb_versions.values()
            if item.get("status") == "published"
        }
        for assertion in self._store.ontology_assertions.values():
            if assertion.get("subject_entity_id") not in entity_id_set:
                continue
            if assertion.get("status") != "published":
                continue
            if kb_version and assertion.get("kb_version") != kb_version:
                continue
            if assertion.get("kb_version") not in published_version_map:
                continue
            predicate = assertion.get("predicate_type")
            object_value = str(assertion.get("object_value") or "")
            if not predicate or not object_value:
                continue
            key = (str(assertion["subject_entity_id"]), str(predicate), object_value)
            constraints.assertion_sources[key] = self._build_assertion_source(
                assertion,
                published_version_map,
            )

    def _build_assertion_source(
        self,
        assertion: dict[str, Any],
        published_version_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        evidence_ids = [str(item) for item in assertion.get("evidence_ids") or []]
        document_id = assertion.get("document_id")
        document = self._store.guideline_documents.get(document_id) if document_id else None
        version = published_version_map.get(str(assertion.get("kb_version") or ""))
        return {
            "assertion_id": assertion.get("assertion_id"),
            "evidence_ids": evidence_ids,
            "document_id": document_id,
            "source_uri": document.get("source_uri") if document else None,
            "source_title": document.get("title") if document else None,
            "snapshot_uri": version.get("snapshot_uri") if version else None,
        }

    def _fallback_query_contexts(self, terms: list[str], *, kb_version: str | None) -> list[ContextResult]:
        results: list[ContextResult] = []
        term_set = set(terms)
        seen: set[str] = set()

        # Context alias mapping from guideline_import
        from ..services.guideline_import import CONTEXT_SYNONYMS, CONTEXT_DISPLAY

        for entity_id, entity in self._store.ontology_entities.items():
            if entity.get("label") != "Context":
                continue
            if kb_version and entity.get("kb_version") != kb_version:
                continue
            standard_name = str(entity.get("standard_name", ""))
            aliases = [str(a) for a in (entity.get("aliases") or [])]
            context_code = (entity.get("attributes") or {}).get("context_name", standard_name)

            if standard_name in term_set and entity_id not in seen:
                seen.add(entity_id)
                results.append(ContextResult(
                    context_code=context_code,
                    display_name=standard_name,
                    entity_id=entity_id,
                ))
                continue

            for alias in aliases:
                if alias in term_set and entity_id not in seen:
                    seen.add(entity_id)
                    results.append(ContextResult(
                        context_code=context_code,
                        display_name=standard_name,
                        entity_id=entity_id,
                    ))
                    break

        # Also check hardcoded context synonyms
        for term in terms:
            for canonical, synonyms in CONTEXT_SYNONYMS.items():
                if term in synonyms:
                    display = CONTEXT_DISPLAY.get(canonical, canonical)
                    # Check if we already have this context
                    already = any(r.context_code == canonical for r in results)
                    if not already:
                        results.append(ContextResult(
                            context_code=canonical,
                            display_name=display,
                            entity_id=canonical,
                        ))

        return results

    def _fallback_all_entities(self, *, kb_version: str | None) -> list[EntityResult]:
        return [
            self._entity_to_result(entity)
            for entity in self._store.ontology_entities.values()
            if not kb_version or entity.get("kb_version") == kb_version
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _entity_to_result(self, entity: dict[str, Any]) -> EntityResult:
        return EntityResult(
            entity_id=str(entity.get("entity_id", "")),
            label=str(entity.get("label", "Entity")),
            standard_name=str(entity.get("standard_name", "")),
            aliases=[str(a) for a in (entity.get("aliases") or [])],
            kb_version=str(entity.get("kb_version", "")),
            attributes=dict(entity.get("attributes") or {}),
        )

    def _entity_path_node(self, entity: dict[str, Any] | None) -> dict[str, Any] | None:
        if entity is None:
            return None
        return {
            "entity_id": entity.get("entity_id"),
            "label": entity.get("label"),
            "standard_name": entity.get("standard_name"),
            "aliases": [str(alias) for alias in (entity.get("aliases") or [])],
        }

    def _path_node(self, assertion: dict[str, Any], entities: dict[str, dict[str, Any]]) -> dict[str, Any]:
        entity = entities.get(str(assertion.get("object_entity_id")))
        if entity is not None:
            node = self._entity_path_node(entity)
            return node or {}
        return {
            "entity_id": assertion.get("object_entity_id"),
            "label": None,
            "standard_name": assertion.get("object_value"),
        }

    def _formula_herb_roles(
        self,
        formula_id: str,
        by_subject: dict[str, list[dict[str, Any]]],
        entities: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        herbs: list[dict[str, Any]] = []
        for ingredient_rel in by_subject.get(formula_id, []):
            if ingredient_rel.get("predicate_type") != "HAS_INGREDIENT":
                continue
            herb_id = str(ingredient_rel.get("object_entity_id") or "")
            herb = entities.get(herb_id)
            role_names: list[str] = []
            for role_rel in by_subject.get(herb_id, []):
                if role_rel.get("predicate_type") != "HAS_FORMULA_ROLE":
                    continue
                role_names.append(str(role_rel.get("object_value") or ""))
            herbs.append({
                "herb": self._entity_path_node(herb),
                "roles": sorted(set(role_names)),
            })
        return herbs

    def _rows_to_entities(self, rows: list[Any]) -> list[EntityResult]:
        results: list[EntityResult] = []
        for row in rows:
            results.append(EntityResult(
                entity_id=row["entity_id"],
                label=row.get("label") or "Entity",
                standard_name=row.get("standard_name") or "",
                aliases=list(row.get("aliases") or []),
                kb_version=row.get("kb_version") or "",
                attributes=self._parse_json(row.get("attributes_json")),
            ))
        return results

    @staticmethod
    def _parse_json(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            import json
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _get_neo4j_driver(self):
        """Get the Neo4j driver from the DatabaseBackedStore, or None."""
        if hasattr(self._store, "_get_neo4j_driver"):
            try:
                return self._store._get_neo4j_driver()
            except Exception:
                return None
        return None

    def _neo4j_database(self) -> str:
        if hasattr(self._store, "settings"):
            return getattr(self._store.settings, "neo4j_database", "neo4j")
        return "neo4j"

    def _active_kb_version_code(self) -> str | None:
        published = [
            item for item in self._store.kb_versions.values()
            if item.get("status") == "published"
        ]
        if not published:
            return None
        active = sorted(
            published,
            key=lambda item: item.get("published_at") or item.get("updated_at") or item.get("created_at"),
            reverse=True,
        )[0]
        return str(active.get("version_code") or "")
