from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Iterable

from ..store import InMemoryStore


@dataclass(frozen=True, slots=True)
class ResolvedConcept:
    concept_id: str
    standard_name: str
    concept_type: str
    surface_text: str
    aliases: tuple[str, ...] = ()
    attributes: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))
    alias_id: str | None = None
    kb_version: str | None = None
    source: str = "ontology_entity"
    score: float = 1.0


class TerminologyResolver:
    def resolve(
        self,
        surface_text: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
    ) -> list[ResolvedConcept]:
        raise NotImplementedError

    def find_mentions(
        self,
        text: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
        min_length: int = 1,
    ) -> list[ResolvedConcept]:
        raise NotImplementedError

    def resolve_by_attribute(
        self,
        attribute_key: str,
        attribute_value: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
    ) -> list[ResolvedConcept]:
        raise NotImplementedError


class EmptyTerminologyResolver(TerminologyResolver):
    def resolve(
        self,
        surface_text: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
    ) -> list[ResolvedConcept]:
        return []

    def find_mentions(
        self,
        text: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
        min_length: int = 1,
    ) -> list[ResolvedConcept]:
        return []

    def resolve_by_attribute(
        self,
        attribute_key: str,
        attribute_value: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
    ) -> list[ResolvedConcept]:
        return []


class StoreTerminologyResolver(TerminologyResolver):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def resolve(
        self,
        surface_text: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
    ) -> list[ResolvedConcept]:
        term = self._normalize(surface_text)
        if not term:
            return []
        matches: dict[str, ResolvedConcept] = {}
        for concept in self._iter_concepts(concept_types=concept_types, kb_version=kb_version):
            concept_id = str(concept.get("entity_id") or "")
            standard_name = str(concept.get("standard_name") or "")
            if self._normalize(standard_name) == term:
                matches[concept_id] = self._to_resolved(concept, term, source="standard_name")
            for alias_text in concept.get("aliases") or []:
                if self._normalize(str(alias_text)) == term:
                    matches[concept_id] = self._to_resolved(concept, str(alias_text), source="entity_alias")
        for alias_id, alias in self._store.concept_aliases.items():
            if str(alias.get("status") or "") not in {"published", "draft"}:
                continue
            if self._normalize(str(alias.get("alias_text") or "")) != term:
                continue
            concept_id = str(alias.get("concept_entity_id") or alias.get("concept_id") or "")
            concept = self._store.ontology_entities.get(concept_id)
            if not self._concept_allowed(concept, concept_types=concept_types, kb_version=kb_version):
                continue
            matches[concept_id] = self._to_resolved(
                concept,
                str(alias.get("alias_text") or term),
                alias_id=str(alias_id),
                source="concept_alias",
            )
        return sorted(matches.values(), key=lambda item: (item.concept_type, item.standard_name, item.concept_id))

    def find_mentions(
        self,
        text: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
        min_length: int = 1,
    ) -> list[ResolvedConcept]:
        haystack = text or ""
        terms: dict[str, list[ResolvedConcept]] = {}
        for concept in self._iter_concepts(concept_types=concept_types, kb_version=kb_version):
            for term in self._concept_terms(concept):
                if len(term) >= min_length:
                    terms.setdefault(term, []).append(self._to_resolved(concept, term, source="terminology_scan"))
        for alias_id, alias in self._store.concept_aliases.items():
            if str(alias.get("status") or "") not in {"published", "draft"}:
                continue
            concept_id = str(alias.get("concept_entity_id") or alias.get("concept_id") or "")
            concept = self._store.ontology_entities.get(concept_id)
            if not self._concept_allowed(concept, concept_types=concept_types, kb_version=kb_version):
                continue
            term = str(alias.get("alias_text") or "").strip()
            if len(term) >= min_length:
                terms.setdefault(term, []).append(
                    self._to_resolved(concept, term, alias_id=str(alias_id), source="terminology_scan")
                )
        hits: dict[tuple[str, str], ResolvedConcept] = {}
        for term in sorted(terms, key=len, reverse=True):
            if term and term in haystack:
                for item in terms[term]:
                    hits[(item.concept_id, term)] = item
        return sorted(hits.values(), key=lambda item: (-len(item.surface_text), item.concept_type, item.standard_name))

    def resolve_by_attribute(
        self,
        attribute_key: str,
        attribute_value: str,
        *,
        concept_types: set[str] | None = None,
        kb_version: str | None = None,
    ) -> list[ResolvedConcept]:
        key = str(attribute_key or "").strip()
        value = str(attribute_value or "").strip()
        if not key or not value:
            return []
        matches: list[ResolvedConcept] = []
        for concept in self._iter_concepts(concept_types=concept_types, kb_version=kb_version):
            if str((concept.get("attributes") or {}).get(key) or "").strip() == value:
                matches.append(self._to_resolved(concept, value, source="concept_attribute"))
        return sorted(matches, key=lambda item: (item.concept_type, item.standard_name, item.concept_id))

    def _iter_concepts(
        self,
        *,
        concept_types: set[str] | None,
        kb_version: str | None,
    ) -> Iterable[dict]:
        for concept in self._store.ontology_entities.values():
            if self._concept_allowed(concept, concept_types=concept_types, kb_version=kb_version):
                yield concept

    def _concept_allowed(
        self,
        concept: dict | None,
        *,
        concept_types: set[str] | None,
        kb_version: str | None,
    ) -> bool:
        if concept is None:
            return False
        if concept_types and str(concept.get("label") or "") not in concept_types:
            return False
        if kb_version and str(concept.get("kb_version") or "") != kb_version:
            return False
        return True

    def _concept_terms(self, concept: dict) -> list[str]:
        values = [str(concept.get("standard_name") or "")]
        values.extend(str(alias) for alias in (concept.get("aliases") or []))
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    def _to_resolved(
        self,
        concept: dict,
        surface_text: str,
        *,
        alias_id: str | None = None,
        source: str,
    ) -> ResolvedConcept:
        return ResolvedConcept(
            concept_id=str(concept.get("entity_id") or ""),
            standard_name=str(concept.get("standard_name") or ""),
            concept_type=str(concept.get("label") or "Concept"),
            surface_text=surface_text,
            aliases=tuple(term for term in self._concept_terms(concept) if term != str(concept.get("standard_name") or "")),
            attributes=MappingProxyType(dict(concept.get("attributes") or {})),
            alias_id=alias_id,
            kb_version=str(concept.get("kb_version") or "") or None,
            source=source,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return str(value or "").strip()
