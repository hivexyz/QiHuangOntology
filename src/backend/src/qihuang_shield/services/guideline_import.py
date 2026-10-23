from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import re
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Iterable
from xml.etree import ElementTree

from .relation_schema import (
    RelationSchemaRegistry,
    canonical_relation_code,
    default_relation_schema_records,
)
from .terminology import EmptyTerminologyResolver, TerminologyResolver

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - exercised via runtime dependency checks
    PdfReader = None


STOPWORDS = {
    "指南",
    "共识",
    "建议",
    "推荐",
    "禁忌",
    "功效",
    "主治",
    "适应证",
    "适应症",
    "人群",
    "场景",
    "内容",
    "患者",
    "医师",
    "医师指导",
    "治疗",
    "食疗",
    "茶饮",
    "孕妇",
    "儿童",
    "老人",
    "老年人",
    "哺乳期",
    "别名",
    "又名",
    "适用于",
    "可用于",
    "禁用于",
    "不宜用于",
    "慎用于",
    "不宜与",
    "具有",
    "以及",
    "其中",
    "此外",
    "但是",
    "然而",
    "同时",
}

MATERIAL_HINTS = (
    "别名",
    "功效",
    "主治",
    "适应证",
    "适应症",
    "禁用于",
    "不宜用于",
    "慎用于",
    "可用于",
    "适用于",
    "配伍禁忌",
    "不宜与",
    "同用",
    "同服",
)

TCM_FIELD_HINTS = (
    "证候",
    "证型",
    "病机",
    "治则",
    "治法",
    "方剂",
    "性味",
    "归经",
    "腧穴",
    "穴位",
    "君药",
    "臣药",
    "佐药",
    "使药",
    "体质",
    "时令",
    "季节",
    "剂量",
    "用量",
    "用法",
)

FORMULA_ROLE_DISPLAY = {
    "monarch": "君药",
    "minister": "臣药",
    "assistant": "佐药",
    "courier": "使药",
}

MATERIAL_PREFIX = "mat"
EFFECT_PREFIX = "eff"
POPULATION_PREFIX = "pop"
CONTEXT_PREFIX = "ctx"
SYNDROME_PREFIX = "syn"
PATHOGENESIS_PREFIX = "path"
PRINCIPLE_PREFIX = "prin"
METHOD_PREFIX = "method"
USAGE_PREFIX = "usage"
PROPERTY_PREFIX = "prop"
NATURE_FLAVOR_PREFIX = "nf"
MERIDIAN_PREFIX = "mer"
MERIDIAN_SYSTEM_PREFIX = "mersys"
ZANGFU_PREFIX = "zangfu"
ACUPOINT_PREFIX = "acu"
CONSTITUTION_PREFIX = "cons"
SEASON_PREFIX = "season"
STAGE_PREFIX = "stage"
DOSE_PREFIX = "dose"
ROLE_PREFIX = "role"

RELATION_CONSTRAINTS = default_relation_schema_records()

FIVE_ELEMENT_GENERATES = {
    "wood": "fire",
    "fire": "earth",
    "earth": "metal",
    "metal": "water",
    "water": "wood",
}

FIVE_ELEMENT_RESTRICTS = {
    "wood": "earth",
    "earth": "water",
    "water": "fire",
    "fire": "metal",
    "metal": "wood",
}

MERIDIAN_ORGANS = {
    "lung": "organ_lung",
    "spleen": "organ_spleen",
    "heart": "organ_heart",
    "kidney": "organ_kidney",
    "liver": "organ_liver",
    "stomach": "organ_stomach",
    "large_intestine": "organ_large_intestine",
    "small_intestine": "organ_small_intestine",
    "bladder": "organ_bladder",
    "gallbladder": "organ_gallbladder",
    "pericardium": "organ_pericardium",
    "triple_energizer": "organ_triple_energizer",
}

EXTRAORDINARY_VESSELS = {"du", "ren", "chong", "dai", "yinwei", "yangwei", "yinqiao", "yangqiao"}

TWELVE_PRIMARY_MERIDIAN_FLOW = [
    "lung",
    "large_intestine",
    "stomach",
    "spleen",
    "heart",
    "small_intestine",
    "bladder",
    "kidney",
    "pericardium",
    "triple_energizer",
    "gallbladder",
    "liver",
]

ORGAN_DISPLAY = {
    "organ_lung": "肺",
    "organ_spleen": "脾",
    "organ_heart": "心",
    "organ_kidney": "肾",
    "organ_liver": "肝",
    "organ_stomach": "胃",
    "organ_large_intestine": "大肠",
    "organ_small_intestine": "小肠",
    "organ_bladder": "膀胱",
    "organ_gallbladder": "胆",
    "organ_pericardium": "心包",
    "organ_triple_energizer": "三焦",
}

MERIDIAN_SYSTEM_DISPLAY = {
    "twelve_primary": "十二经脉",
    "extraordinary_vessel": "奇经八脉",
}


@dataclass(slots=True)
class MaterialDraft:
    name: str
    aliases: set[str] = field(default_factory=set)
    effects: set[str] = field(default_factory=set)
    diseases: set[str] = field(default_factory=set)
    symptoms: set[str] = field(default_factory=set)
    patterns: set[str] = field(default_factory=set)
    syndromes: set[str] = field(default_factory=set)
    pathogenesis: set[str] = field(default_factory=set)
    treatment_principles: set[str] = field(default_factory=set)
    treatment_methods: set[str] = field(default_factory=set)
    usage_methods: set[str] = field(default_factory=set)
    formulas: set[str] = field(default_factory=set)
    properties: set[str] = field(default_factory=set)
    meridians: set[str] = field(default_factory=set)
    acupoints: set[str] = field(default_factory=set)
    constitutions: set[str] = field(default_factory=set)
    seasons: set[str] = field(default_factory=set)
    stages: set[str] = field(default_factory=set)
    doses: set[str] = field(default_factory=set)
    formula_roles: dict[str, set[str]] = field(default_factory=dict)
    acupoint_locations: dict[str, str] = field(default_factory=dict)
    acupoint_methods: dict[str, str] = field(default_factory=dict)
    acupoint_pairs: dict[str, set[str]] = field(default_factory=dict)
    not_for_populations: set[str] = field(default_factory=set)
    allowed_contexts: set[str] = field(default_factory=set)
    prohibited_contexts: set[str] = field(default_factory=set)
    contraindications: set[str] = field(default_factory=set)
    evidence: list[str] = field(default_factory=list)
    unresolved_terms: dict[str, set[str]] = field(default_factory=dict)


@dataclass(slots=True)
class GuidelineOntologyBundle:
    ontology_entities: dict[str, dict[str, Any]]
    knowledge_cards: dict[str, dict[str, Any]]
    warnings: list[str]
    extracted_materials: list[str]
    relationship_count: int
    ontology_assertions: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence_sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    concept_aliases: dict[str, dict[str, Any]] = field(default_factory=dict)
    guideline_documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    mentions: dict[str, dict[str, Any]] = field(default_factory=dict)
    normalization_decisions: dict[str, dict[str, Any]] = field(default_factory=dict)
    condition_sets: dict[str, dict[str, Any]] = field(default_factory=dict)
    extractor_engine: str = "rule"
    extractor_model: str | None = None
    extractor_prompt_version: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    extraction_stats: dict[str, Any] = field(default_factory=dict)


class GuidelineOntologyExtractor:
    def __init__(self, terminology_resolver: TerminologyResolver | None = None) -> None:
        self.terminology_resolver = terminology_resolver or EmptyTerminologyResolver()

    def extract(
        self, guide_title: str, guide_text: str, kb_version: str
    ) -> GuidelineOntologyBundle:
        text = self._normalize_text(guide_text)
        material_names = self._collect_material_candidates(text)
        if not material_names:
            return GuidelineOntologyBundle(
                ontology_entities={},
                knowledge_cards={},
                ontology_assertions={},
                evidence_sources={},
                concept_aliases={},
                guideline_documents={},
                mentions={},
                normalization_decisions={},
                condition_sets={},
                warnings=[
                    "未识别到明确的中药/方药实体；请尽量使用结构化文本或在句子中明确药材名。"
                ],
                extracted_materials=[],
                relationship_count=0,
                extractor_engine="rule",
                extraction_stats=self._build_extraction_stats(
                    guide_text=text,
                    material_names=[],
                    relationship_count=0,
                    knowledge_card_count=0,
                    warning_count=1,
                    source_kind="rule",
                ),
            )
        drafts = {name: MaterialDraft(name=name) for name in material_names}
        current_material: str | None = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            section_name = self._extract_section_material_name(stripped)
            if section_name and section_name in drafts:
                current_material = section_name

            clauses = [item.strip() for item in re.split(r"[。；;]+", stripped) if item.strip()]
            for clause in clauses:
                material_name = self._infer_primary_material(
                    clause, material_names, current_material
                )
                if not material_name:
                    continue
                current_material = material_name
                draft = drafts[material_name]
                if clause not in draft.evidence:
                    draft.evidence.append(clause)
                draft.aliases.update(self._extract_aliases(clause, material_name))
                draft.effects.update(self._extract_effects(clause))
                self._extract_tcm_core_fields(clause, draft)
                if self._has_negative_cue(clause):
                    draft.not_for_populations.update(self._extract_populations(clause))
                    draft.prohibited_contexts.update(self._extract_contexts(clause))
                if self._has_positive_context_cue(clause):
                    draft.allowed_contexts.update(self._extract_contexts(clause))
                draft.contraindications.update(
                    self._extract_contraindications(clause, material_name, material_names)
                )

        return self._build_bundle(
            drafts=drafts,
            material_names=material_names,
            guide_title=guide_title,
            kb_version=kb_version,
            warnings=[],
            extractor_engine="rule",
            guide_text=text,
        )

    def build_bundle_from_materials(
        self,
        guide_title: str,
        kb_version: str,
        materials: Iterable[dict[str, Any]],
        warnings: list[str] | None = None,
        extractor_engine: str = "llm",
        extractor_model: str | None = None,
        extractor_prompt_version: str | None = None,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        guide_text: str | None = None,
    ) -> GuidelineOntologyBundle:
        drafts: dict[str, MaterialDraft] = {}
        normalized_warnings = list(warnings or [])

        for material in materials:
            if not isinstance(material, dict):
                continue
            material_name = self._clean_candidate_name(str(material.get("name") or ""))
            if not material_name:
                continue
            draft = drafts.setdefault(material_name, MaterialDraft(name=material_name))

            for alias in self._normalize_string_values(material.get("aliases")):
                cleaned_alias = self._clean_text_value(alias, max_length=24)
                if cleaned_alias and cleaned_alias != material_name:
                    draft.aliases.add(cleaned_alias)

            for effect in self._normalize_string_values(material.get("effects")):
                cleaned_effect = self._clean_text_value(effect, max_length=32)
                if cleaned_effect:
                    draft.effects.add(cleaned_effect)
            for disease in self._normalize_string_values(material.get("diseases")):
                canonical = self._canonicalize_disease(disease)
                if canonical:
                    draft.diseases.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("disease", set()).add(disease)
            for symptom in self._normalize_string_values(material.get("symptoms")):
                canonical = self._canonicalize_symptom(symptom)
                if canonical:
                    draft.symptoms.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("symptom", set()).add(symptom)
            for pattern in self._normalize_string_values(material.get("patterns")):
                canonical = self._canonicalize_pattern(pattern)
                if canonical:
                    draft.patterns.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("pattern", set()).add(pattern)

            for syndrome in self._normalize_string_values(material.get("syndromes")):
                canonical = self._canonicalize_pattern(syndrome)
                if canonical:
                    draft.patterns.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("pattern", set()).add(syndrome)
            for pathogenesis in self._normalize_string_values(material.get("pathogenesis")):
                canonical = self._canonicalize_pathogenesis(pathogenesis)
                if canonical:
                    draft.pathogenesis.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("pathogenesis", set()).add(pathogenesis)
            for principle in self._normalize_string_values(material.get("treatment_principles")):
                cleaned = self._clean_text_value(principle, max_length=32)
                if cleaned:
                    draft.treatment_principles.add(cleaned)
            for method in self._normalize_string_values(material.get("treatment_methods")):
                cleaned = self._clean_text_value(method, max_length=32)
                if cleaned:
                    draft.treatment_methods.add(cleaned)
            for usage_method in self._normalize_string_values(material.get("usage_methods")):
                canonical = self._canonicalize_usage_method(usage_method)
                if canonical:
                    draft.usage_methods.add(canonical)
            for formula in self._normalize_string_values(material.get("formulas")):
                cleaned = self._clean_candidate_name(formula)
                if cleaned:
                    draft.formulas.add(cleaned)
                    drafts.setdefault(cleaned, MaterialDraft(name=cleaned))
            for property_name in self._normalize_string_values(material.get("properties")):
                canonical = self._canonicalize_property(property_name)
                if canonical:
                    draft.properties.add(canonical)
            for meridian in self._normalize_string_values(material.get("meridians")):
                canonical = self._canonicalize_meridian(meridian)
                if canonical:
                    draft.meridians.add(canonical)
            for constitution in self._normalize_string_values(material.get("constitutions")):
                canonical = self._canonicalize_constitution(constitution)
                if canonical:
                    draft.constitutions.add(canonical)
            for season in self._normalize_string_values(material.get("seasons")):
                canonical = self._canonicalize_season(season)
                if canonical:
                    draft.seasons.add(canonical)
            for dose in self._normalize_string_values(material.get("doses")):
                cleaned = self._clean_text_value(dose, max_length=24)
                if cleaned:
                    draft.doses.add(cleaned)
            self._merge_formula_roles(draft, material.get("formula_roles"))

            for context in self._normalize_string_values(material.get("allowed_contexts")):
                canonical = self._canonicalize_context(context)
                if canonical:
                    draft.allowed_contexts.add(canonical)
            for context in self._normalize_string_values(material.get("prohibited_contexts")):
                canonical = self._canonicalize_context(context)
                if canonical:
                    draft.prohibited_contexts.add(canonical)

            for population in self._normalize_string_values(material.get("not_for_populations")):
                canonical = self._canonicalize_population(population)
                if canonical:
                    draft.not_for_populations.add(canonical)

            for contraindication_name in self._extract_contraindication_names(
                material.get("contraindications")
            ):
                cleaned_target = self._clean_candidate_name(contraindication_name)
                if cleaned_target and cleaned_target != material_name:
                    draft.contraindications.add(cleaned_target)
                    drafts.setdefault(cleaned_target, MaterialDraft(name=cleaned_target))

            for evidence in self._normalize_string_values(
                material.get("evidence"), split_inline=False
            ):
                cleaned_evidence = self._clean_text_value(evidence, max_length=200)
                if cleaned_evidence and cleaned_evidence not in draft.evidence:
                    draft.evidence.append(cleaned_evidence)

        if not drafts:
            return GuidelineOntologyBundle(
                ontology_entities={},
                knowledge_cards={},
                ontology_assertions={},
                evidence_sources={},
                concept_aliases={},
                guideline_documents={},
                mentions={},
                normalization_decisions={},
                condition_sets={},
                warnings=[*normalized_warnings, "未识别到可入库的中药/方药实体。"],
                extracted_materials=[],
                relationship_count=0,
                extractor_engine=extractor_engine,
                extractor_model=extractor_model,
                extractor_prompt_version=extractor_prompt_version,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                extraction_stats=self._build_extraction_stats(
                    guide_text=guide_text or "",
                    material_names=[],
                    relationship_count=0,
                    knowledge_card_count=0,
                    warning_count=len(normalized_warnings) + 1,
                    source_kind=extractor_engine,
                ),
            )

        material_names = sorted(drafts)
        return self._build_bundle(
            drafts=drafts,
            material_names=material_names,
            guide_title=guide_title,
            kb_version=kb_version,
            warnings=normalized_warnings,
            extractor_engine=extractor_engine,
            extractor_model=extractor_model,
            extractor_prompt_version=extractor_prompt_version,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            guide_text=guide_text or "",
        )

    def build_bundle_from_candidate_envelope(
        self,
        guide_title: str,
        kb_version: str,
        candidate_envelope: dict[str, Any],
        warnings: list[str] | None = None,
        extractor_engine: str = "llm",
        extractor_model: str | None = None,
        extractor_prompt_version: str | None = None,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
        guide_text: str | None = None,
        validation_stats: dict[str, Any] | None = None,
    ) -> GuidelineOntologyBundle:
        materials = candidate_envelope.get("_legacy_materials")
        if isinstance(materials, list):
            bundle = self.build_bundle_from_materials(
                guide_title=guide_title,
                kb_version=kb_version,
                materials=materials,
                warnings=warnings,
                extractor_engine=extractor_engine,
                extractor_model=extractor_model,
                extractor_prompt_version=extractor_prompt_version,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                guide_text=guide_text,
            )
            bundle.extraction_stats.update(
                self._candidate_contract_stats(candidate_envelope, validation_stats, {})
            )
            return bundle

        return self._build_bundle_from_native_candidate_envelope(
            guide_title=guide_title,
            kb_version=kb_version,
            candidate_envelope=candidate_envelope,
            warnings=warnings,
            extractor_engine=extractor_engine,
            extractor_model=extractor_model,
            extractor_prompt_version=extractor_prompt_version,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            guide_text=guide_text or "",
            validation_stats=validation_stats,
        )

    def _build_bundle_from_native_candidate_envelope(
        self,
        *,
        guide_title: str,
        kb_version: str,
        candidate_envelope: dict[str, Any],
        warnings: list[str] | None,
        extractor_engine: str,
        extractor_model: str | None,
        extractor_prompt_version: str | None,
        fallback_used: bool,
        fallback_reason: str | None,
        guide_text: str,
        validation_stats: dict[str, Any] | None,
    ) -> GuidelineOntologyBundle:
        ontology_entities: dict[str, dict[str, Any]] = {}
        knowledge_cards: dict[str, dict[str, Any]] = {}
        ontology_assertions: dict[str, dict[str, Any]] = {}
        evidence_sources: dict[str, dict[str, Any]] = {}
        concept_aliases: dict[str, dict[str, Any]] = {}
        guideline_documents: dict[str, dict[str, Any]] = {}
        mentions: dict[str, dict[str, Any]] = {}
        normalization_decisions: dict[str, dict[str, Any]] = {}
        condition_sets: dict[str, dict[str, Any]] = {}
        drop_stats: dict[str, int] = {}
        merged_warnings = list(warnings or [])
        now = datetime.now(timezone.utc)

        document_id = self._document_id(guide_title, kb_version)
        guideline_documents[document_id] = {
            "document_id": document_id,
            "kb_version": kb_version,
            "source_uri": guide_title,
            "title": guide_title,
            "source_type": "guideline_import",
            "status": "draft",
        }

        mention_by_id: dict[str, dict[str, Any]] = {}
        for item in candidate_envelope.get("mentions") or []:
            mention_id = str(item.get("mention_id") or "").strip()
            if not mention_id:
                self._increment_drop(drop_stats, "dropped_mention_missing_id")
                continue
            span = item.get("source_span") or {}
            mention = {
                "mention_id": mention_id,
                "source_type": "llm_candidate_contract",
                "source_record_id": kb_version,
                "surface_text": str(item.get("text") or ""),
                "normalized_text": str(item.get("text") or "").strip(),
                "start_offset": int(span.get("start") or 0),
                "end_offset": int(span.get("end") or 0),
                "mention_type_guess": str(item.get("concept_type") or "").lower() or None,
                "context_window": guide_text[max(0, int(span.get("start") or 0) - 30): min(len(guide_text), int(span.get("end") or 0) + 30)],
                "kb_version": kb_version,
                "created_at": now,
            }
            mentions[mention_id] = mention
            mention_by_id[mention_id] = mention

        evidence_by_id: dict[str, dict[str, Any]] = {}
        for item in candidate_envelope.get("evidence_spans") or []:
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id:
                self._increment_drop(drop_stats, "dropped_evidence_missing_id")
                continue
            evidence = {
                "evidence_id": evidence_id,
                "kb_version": kb_version,
                "source_type": "llm_span",
                "source_uri": guide_title,
                "source_title": guide_title,
                "source_text": str(item.get("text") or ""),
                "entity_id": None,
                "status": "draft",
                "document_id": document_id,
                "start_offset": int(item.get("start") or 0),
                "end_offset": int(item.get("end") or 0),
            }
            evidence_sources[evidence_id] = evidence
            evidence_by_id[evidence_id] = evidence

        candidate_by_id: dict[str, dict[str, Any]] = {}
        candidates_by_mention: dict[str, list[dict[str, Any]]] = {}
        for item in candidate_envelope.get("concept_candidates") or []:
            candidate_id = str(item.get("candidate_id") or "").strip()
            mention_id = str(item.get("mention_id") or "").strip()
            name = str(item.get("name") or "").strip()
            label = str(item.get("concept_type") or "Concept").strip() or "Concept"
            if not candidate_id or not name:
                self._increment_drop(drop_stats, "dropped_concept_missing_required_field")
                continue
            entity_id = self._candidate_entity_id(label, name, kb_version, candidate_id)
            mention = mention_by_id.get(mention_id)
            aliases = []
            if mention is not None:
                surface_text = str(mention.get("surface_text") or "").strip()
                if surface_text and surface_text != name:
                    aliases.append(surface_text)
            entity = {
                "entity_id": entity_id,
                "label": label,
                "standard_name": name,
                "aliases": aliases,
                "kb_version": kb_version,
                "attributes": {
                    "candidate_id": candidate_id,
                    "mention_id": mention_id,
                    "confidence": item.get("confidence"),
                    "extractor_engine": extractor_engine,
                },
            }
            ontology_entities[entity_id] = entity
            candidate = {**item, "entity_id": entity_id, "entity": entity}
            candidate_by_id[candidate_id] = candidate
            candidates_by_mention.setdefault(mention_id, []).append(candidate)
            if aliases:
                alias_text = aliases[0]
                alias_id = self._alias_id(entity_id, alias_text, kb_version)
                concept_aliases[alias_id] = {
                    "alias_id": alias_id,
                    "alias_text": alias_text,
                    "concept_entity_id": entity_id,
                    "canonical_name": name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "alias_type": "llm_candidate_alias",
                }

        for mention_id, candidates in candidates_by_mention.items():
            candidate_list = [
                {
                    "concept_id": candidate["entity_id"],
                    "candidate_id": candidate.get("candidate_id"),
                    "canonical_name": candidate.get("name"),
                    "concept_type": candidate.get("concept_type"),
                    "score": float(candidate.get("confidence", 0.0) or 0.0),
                }
                for candidate in sorted(
                    candidates,
                    key=lambda item: (-float(item.get("confidence", 0.0) or 0.0), str(item.get("name") or "")),
                )
            ]
            is_ambiguous = len(candidate_list) > 1
            chosen = candidate_list[0] if candidate_list else {}
            decision_id = f"normdec_{hashlib.md5((mention_id + 'llm').encode('utf-8')).hexdigest()[:16]}"
            normalization_decisions[decision_id] = {
                "decision_id": decision_id,
                "mention_id": mention_id,
                "resolved_concept_id": None if is_ambiguous else chosen.get("concept_id"),
                "canonical_name": None if is_ambiguous else chosen.get("canonical_name"),
                "resolver_type": "llm_candidate_contract",
                "resolver_version": str(candidate_envelope.get("contract_version") or ""),
                "confidence_score": float(chosen.get("score", 0.0) or 0.0) if not is_ambiguous else 0.5,
                "candidate_list": candidate_list,
                "decision_reason": "ambiguous llm candidate mention" if is_ambiguous else "resolved from llm candidate contract",
                "status": "ambiguous" if is_ambiguous else "resolved",
                "kb_version": kb_version,
                "created_at": now,
            }

        condition_ids_by_candidate: dict[str, list[str]] = {}
        for item in candidate_envelope.get("condition_candidates") or []:
            condition_id = str(item.get("condition_id") or "").strip()
            if not condition_id:
                self._increment_drop(drop_stats, "dropped_condition_missing_id")
                continue
            candidate_id = str(item.get("candidate_id") or "").strip()
            mention_id = str(item.get("mention_id") or "").strip()
            target_candidate = candidate_by_id.get(candidate_id) if candidate_id else None
            target_mention = mention_by_id.get(mention_id) if mention_id else None
            if target_candidate is None and target_mention is None:
                self._increment_drop(drop_stats, "dropped_condition_missing_target")
                continue
            evidence_ids = self._candidate_evidence_ids(item.get("evidence_span_ids"), evidence_by_id)
            condition_set_id = f"cond_llm_{hashlib.md5((condition_id + kb_version).encode('utf-8')).hexdigest()[:16]}"
            condition_type = str(item.get("condition_type") or target_candidate.get("concept_type") if target_candidate else target_mention.get("mention_type_guess") or "context")
            condition_item: dict[str, Any] = {
                "type": condition_type,
                "operator": "equals",
                "polarity": item.get("polarity"),
                "evidence_ids": evidence_ids,
            }
            if target_candidate is not None:
                condition_item.update(
                    {
                        "value": target_candidate.get("name"),
                        "value_type": "concept",
                        "normalized_concept_id": target_candidate["entity_id"],
                    }
                )
                condition_ids_by_candidate.setdefault(str(target_candidate.get("candidate_id")), []).append(condition_set_id)
            else:
                condition_item.update(
                    {
                        "value": target_mention.get("surface_text"),
                        "value_type": "mention",
                        "mention_id": mention_id,
                    }
                )
            condition_sets[condition_set_id] = {
                "condition_set_id": condition_set_id,
                "logic": {"all": [condition_item]},
                "note": "LLM candidate condition",
            }

        relationship_count = 0
        for item in candidate_envelope.get("assertion_candidates") or []:
            subject = candidate_by_id.get(str(item.get("subject_candidate_id") or ""))
            obj = candidate_by_id.get(str(item.get("object_candidate_id") or ""))
            relation_code = canonical_relation_code(str(item.get("relation_code") or ""))
            if subject is None or obj is None:
                self._increment_drop(drop_stats, "dropped_assertion_missing_candidate")
                continue
            relation = RELATION_CONSTRAINTS.get(relation_code)
            if relation is None:
                self._increment_drop(drop_stats, "dropped_relation_code")
                continue
            if subject["entity"].get("label") not in set(relation.get("subject_labels") or []):
                self._increment_drop(drop_stats, "dropped_by_subject_type")
                continue
            if obj["entity"].get("label") not in set(relation.get("object_labels") or []):
                self._increment_drop(drop_stats, "dropped_by_object_type")
                continue
            evidence_ids = self._candidate_evidence_ids(item.get("evidence_span_ids"), evidence_by_id)
            if relation.get("evidence_required", True) and not evidence_ids:
                self._increment_drop(drop_stats, "dropped_missing_evidence")
                continue
            assertion_id = self._candidate_assertion_id(
                str(item.get("assertion_id") or ""),
                subject["entity_id"],
                relation_code,
                obj["entity_id"],
                kb_version,
            )
            assertion = {
                "assertion_id": assertion_id,
                "subject_entity_id": subject["entity_id"],
                "predicate_type": relation_code,
                "object_entity_id": obj["entity_id"],
                "object_value": obj.get("name"),
                "kb_version": kb_version,
                "status": "draft",
                "source_guide": guide_title,
                "evidence_ids": evidence_ids,
                "document_id": document_id,
                "polarity": item.get("polarity"),
                "candidate_assertion_id": item.get("assertion_id"),
            }
            linked_condition_ids = [
                *condition_ids_by_candidate.get(str(item.get("subject_candidate_id") or ""), []),
                *condition_ids_by_candidate.get(str(item.get("object_candidate_id") or ""), []),
            ]
            if linked_condition_ids:
                assertion["condition_set_id"] = linked_condition_ids[0]
            ontology_assertions[assertion_id] = assertion
            relationship_count += 1

        for entity_id, entity in ontology_entities.items():
            if entity.get("label") not in {"Material", "Herb", "Formula"}:
                continue
            assertion_count = sum(
                1 for assertion in ontology_assertions.values() if assertion.get("subject_entity_id") == entity_id
            )
            evidence_count = len(
                {
                    evidence_id
                    for assertion in ontology_assertions.values()
                    if assertion.get("subject_entity_id") == entity_id
                    for evidence_id in assertion.get("evidence_ids", [])
                }
            )
            knowledge_cards[entity_id] = {
                "entity": {
                    "entity_id": entity_id,
                    "standard_name": entity.get("standard_name"),
                    "label": entity.get("label"),
                },
                "aliases": list(entity.get("aliases") or []),
                "kb_version": kb_version,
                "source_guide": guide_title,
                "assertion_count": assertion_count,
                "evidence_count": evidence_count,
                "derived_from_assertions": True,
            }

        material_names = sorted(
            str(entity.get("standard_name") or "")
            for entity in ontology_entities.values()
            if entity.get("label") in {"Material", "Herb", "Formula"}
        )
        if drop_stats:
            merged_warnings.extend(
                f"LLM candidate dropped: {reason}={count}" for reason, count in sorted(drop_stats.items())
            )
        extraction_stats = self._build_extraction_stats(
            guide_text=guide_text,
            material_names=material_names,
            relationship_count=relationship_count,
            knowledge_card_count=len(knowledge_cards),
            warning_count=len(merged_warnings),
            source_kind=extractor_engine,
        )
        extraction_stats.update(
            self._candidate_contract_stats(candidate_envelope, validation_stats, drop_stats)
        )
        return GuidelineOntologyBundle(
            ontology_entities=ontology_entities,
            knowledge_cards=knowledge_cards,
            warnings=merged_warnings,
            extracted_materials=material_names,
            relationship_count=relationship_count,
            ontology_assertions=ontology_assertions,
            evidence_sources=evidence_sources,
            concept_aliases=concept_aliases,
            guideline_documents=guideline_documents,
            mentions=mentions,
            normalization_decisions=normalization_decisions,
            condition_sets=condition_sets,
            extractor_engine=extractor_engine,
            extractor_model=extractor_model,
            extractor_prompt_version=extractor_prompt_version,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            extraction_stats=extraction_stats,
        )

    def _candidate_contract_stats(
        self,
        candidate_envelope: dict[str, Any],
        validation_stats: dict[str, Any] | None,
        drop_stats: dict[str, int],
    ) -> dict[str, Any]:
        counts = {
            key: len(value) if isinstance(value, list) else 0
            for key, value in candidate_envelope.items()
            if key
            in {
                "mentions",
                "concept_candidates",
                "assertion_candidates",
                "condition_candidates",
                "evidence_spans",
            }
        }
        return {
            "llm_contract_version": candidate_envelope.get("contract_version"),
            "llm_candidate_counts": counts,
            "llm_candidate_validation": dict(validation_stats or {}),
            "llm_candidate_drop_stats": dict(sorted(drop_stats.items())),
            "llm_candidate_retention": {
                "concepts": counts.get("concept_candidates", 0),
                "assertions": counts.get("assertion_candidates", 0) - sum(
                    count for key, count in drop_stats.items() if key.startswith("dropped_")
                ),
            },
        }

    @staticmethod
    def _increment_drop(drop_stats: dict[str, int], reason: str) -> None:
        drop_stats[reason] = drop_stats.get(reason, 0) + 1

    def _candidate_entity_id(self, label: str, value: str, kb_version: str, candidate_id: str) -> str:
        prefix_by_label = {
            "Material": MATERIAL_PREFIX,
            "Herb": MATERIAL_PREFIX,
            "Formula": MATERIAL_PREFIX,
            "Effect": EFFECT_PREFIX,
            "Population": POPULATION_PREFIX,
            "Context": CONTEXT_PREFIX,
            "Scenario": CONTEXT_PREFIX,
            "Disease": "disease",
            "Symptom": "symptom",
            "Pattern": "pattern",
            "Pathogenesis": PATHOGENESIS_PREFIX,
            "TreatmentPrinciple": PRINCIPLE_PREFIX,
            "TreatmentMethod": METHOD_PREFIX,
            "UsageMethod": USAGE_PREFIX,
            "Property": PROPERTY_PREFIX,
            "NatureFlavor": NATURE_FLAVOR_PREFIX,
            "ZangFu": ZANGFU_PREFIX,
            "Meridian": MERIDIAN_PREFIX,
            "MeridianSystem": MERIDIAN_SYSTEM_PREFIX,
            "Acupoint": ACUPOINT_PREFIX,
            "Constitution": CONSTITUTION_PREFIX,
            "Season": SEASON_PREFIX,
            "Stage": STAGE_PREFIX,
            "Dose": DOSE_PREFIX,
            "FormulaRole": ROLE_PREFIX,
        }
        return self._entity_id(prefix_by_label.get(label, "concept"), f"{value}|{candidate_id}", kb_version)

    @staticmethod
    def _candidate_evidence_ids(value: Any, evidence_by_id: dict[str, dict[str, Any]]) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            evidence_id = str(item)
            if evidence_id in evidence_by_id and evidence_id not in result:
                result.append(evidence_id)
        return result

    def _candidate_assertion_id(
        self,
        candidate_assertion_id: str,
        subject_id: str,
        predicate_type: str,
        object_id: str,
        kb_version: str,
    ) -> str:
        raw = candidate_assertion_id or f"{subject_id}|{predicate_type}|{object_id}|{kb_version}"
        return f"assert_llm_{hashlib.md5((raw + '|' + kb_version).encode('utf-8')).hexdigest()[:16]}"

    def _candidate_envelope_to_materials(
        self, candidate_envelope: dict[str, Any]
    ) -> list[dict[str, Any]]:
        candidates = candidate_envelope.get("concept_candidates") or []
        by_id = {
            str(candidate.get("candidate_id")): candidate
            for candidate in candidates
            if isinstance(candidate, dict) and candidate.get("candidate_id")
        }
        material_types = {"Material", "Herb", "Formula"}
        materials_by_name: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            if (
                not isinstance(candidate, dict)
                or candidate.get("concept_type") not in material_types
            ):
                continue
            name = str(candidate.get("name") or candidate.get("canonical_name") or "").strip()
            if name:
                materials_by_name.setdefault(name, {"name": name})

        evidence_by_id = {
            str(span.get("evidence_id")): span
            for span in candidate_envelope.get("evidence_spans") or []
            if isinstance(span, dict) and span.get("evidence_id")
        }
        for assertion in candidate_envelope.get("assertion_candidates") or []:
            if not isinstance(assertion, dict):
                continue
            subject = by_id.get(str(assertion.get("subject_candidate_id")))
            if not subject:
                continue
            subject_name = str(subject.get("name") or subject.get("canonical_name") or "").strip()
            material = materials_by_name.get(subject_name)
            if not material:
                continue
            relation_code = str(assertion.get("relation_code") or "").strip().upper()
            polarity = assertion.get("polarity")
            if not self._candidate_assertion_is_usable(relation_code, polarity):
                continue
            object_candidate = by_id.get(str(assertion.get("object_candidate_id")))
            object_name = ""
            if object_candidate:
                object_name = str(
                    object_candidate.get("name") or object_candidate.get("canonical_name") or ""
                ).strip()
            if not object_name:
                continue
            self._apply_candidate_relation(material, relation_code, object_name)
            for evidence_id in assertion.get("evidence_span_ids") or []:
                span = evidence_by_id.get(str(evidence_id))
                evidence_text = str(span.get("text") or "").strip() if span else ""
                if evidence_text and evidence_text not in material.setdefault("evidence", []):
                    material["evidence"].append(evidence_text)
        return list(materials_by_name.values())

    def _candidate_assertion_is_usable(self, relation_code: str, polarity: Any) -> bool:
        if relation_code in {
            "NOT_FOR_POPULATION",
            "PROHIBITED_IN_CONTEXT",
            "CONTRAINDICATED_WITH",
        }:
            return polarity == "negative"
        return polarity == "positive"

    def _apply_candidate_relation(
        self, material: dict[str, Any], relation_code: str, object_name: str
    ) -> None:
        field_by_relation = {
            "HAS_EFFECT": "effects",
            "INDICATED_FOR": "effects",
            "INDICATED_FOR_PATTERN": "patterns",
            "INDICATED_FOR_SYMPTOM": "symptoms",
            "INDICATED_FOR_DISEASE": "diseases",
            "NOT_FOR_POPULATION": "not_for_populations",
            "ALLOWED_IN_CONTEXT": "allowed_contexts",
            "PROHIBITED_IN_CONTEXT": "prohibited_contexts",
            "CONTRAINDICATED_WITH": "contraindications",
            "HAS_USAGE_METHOD": "usage_methods",
            "HAS_PROPERTY": "properties",
            "ENTERS_MERIDIAN": "meridians",
            "SUITABLE_FOR_CONSTITUTION": "constitutions",
            "SEASONAL_RELEVANCE": "seasons",
            "SUITABLE_FOR_STAGE": "stages",
            "HAS_DOSE": "doses",
        }
        field = field_by_relation.get(relation_code)
        if field:
            material.setdefault(field, []).append(object_name)

    def decode_guide_file(self, file_name: str, file_base64: str) -> tuple[str, list[str]]:
        warnings: list[str] = []
        suffix = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
        try:
            raw = base64.b64decode(file_base64, validate=True)
        except Exception as exc:
            raise ValueError("guide_file_base64 is not valid base64") from exc

        if suffix in {"txt", "md", "markdown", "csv"}:
            text, used_encoding = self._decode_text_bytes(raw)
            if used_encoding != "utf-8":
                warnings.append(f"文件按 {used_encoding} 编码解码。")
            return text, warnings
        if suffix == "docx":
            return self._extract_docx_text(raw), warnings
        if suffix == "pdf":
            text, pdf_warnings = self._extract_pdf_text(raw)
            warnings.extend(pdf_warnings)
            return text, warnings
        raise ValueError("Only txt/md/csv/docx/pdf files are supported in current MVP")

    def _build_bundle(
        self,
        drafts: dict[str, MaterialDraft],
        material_names: list[str],
        guide_title: str,
        kb_version: str,
        warnings: list[str],
        extractor_engine: str,
        guide_text: str,
        extractor_model: str | None = None,
        extractor_prompt_version: str | None = None,
        fallback_used: bool = False,
        fallback_reason: str | None = None,
    ) -> GuidelineOntologyBundle:
        ontology_entities: dict[str, dict[str, Any]] = {}
        knowledge_cards: dict[str, dict[str, Any]] = {}
        ontology_assertions: dict[str, dict[str, Any]] = {}
        evidence_sources: dict[str, dict[str, Any]] = {}
        concept_aliases: dict[str, dict[str, Any]] = {}
        guideline_documents: dict[str, dict[str, Any]] = {}
        condition_sets: dict[str, dict[str, Any]] = {}
        merged_warnings = list(warnings)
        context_entities: dict[str, dict[str, Any]] = {}
        population_entities: dict[str, dict[str, Any]] = {}
        effect_entities: dict[str, dict[str, Any]] = {}
        tcm_entities: dict[str, dict[str, Any]] = {}
        relationship_count = 0

        document_id = self._document_id(guide_title, kb_version)
        guideline_documents[document_id] = {
            "document_id": document_id,
            "kb_version": kb_version,
            "source_uri": guide_title,
            "title": guide_title,
            "source_type": "guideline_import",
            "status": "draft",
        }

        for material_name in material_names:
            draft = drafts[material_name]
            if not any(
                (
                    draft.aliases,
                    draft.effects,
                    draft.diseases,
                    draft.symptoms,
                    draft.patterns,
                    draft.pathogenesis,
                    draft.treatment_principles,
                    draft.treatment_methods,
                    draft.usage_methods,
                    draft.formulas,
                    draft.properties,
                    draft.meridians,
                    draft.acupoints,
                    draft.constitutions,
                    draft.seasons,
                    draft.stages,
                    draft.doses,
                    any(draft.formula_roles.values()),
                    draft.not_for_populations,
                    draft.allowed_contexts,
                    draft.prohibited_contexts,
                    draft.contraindications,
                )
            ):
                merged_warnings.append(f"实体 {material_name} 仅识别到名称，未提取出明确关系。")

            material_id = self._entity_id(MATERIAL_PREFIX, material_name, kb_version)
            risk_level = (
                "high" if draft.prohibited_contexts or draft.not_for_populations else "medium"
            )
            material_label = self._material_label(material_name)
            ontology_entities[material_id] = {
                "entity_id": material_id,
                "label": material_label,
                "standard_name": material_name,
                "aliases": sorted(draft.aliases),
                "kb_version": kb_version,
                "attributes": {
                    "material_type": material_label.lower(),
                    "risk_level": risk_level,
                    "food_allowed": not bool(draft.prohibited_contexts),
                    "guide_title": guide_title,
                },
            }
            for alias in sorted(draft.aliases):
                alias_id = self._alias_id(material_id, alias, kb_version)
                concept_aliases[alias_id] = {
                    "alias_id": alias_id,
                    "alias_text": alias,
                    "concept_entity_id": material_id,
                    "canonical_name": material_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "alias_type": "material_alias",
                }

            material_evidence_ids: list[str] = []
            for idx, evidence_text in enumerate(draft.evidence[:10], start=1):
                evidence_id = self._evidence_id(material_id, idx, kb_version)
                evidence_sources[evidence_id] = {
                    "evidence_id": evidence_id,
                    "kb_version": kb_version,
                    "source_type": "guideline_clause",
                    "source_uri": guide_title,
                    "source_title": guide_title,
                    "source_text": evidence_text,
                    "entity_id": material_id,
                    "status": "draft",
                    "document_id": document_id,
                }
                material_evidence_ids.append(evidence_id)

            for context_name in sorted(draft.allowed_contexts | draft.prohibited_contexts):
                context_id = self._entity_id(CONTEXT_PREFIX, context_name, kb_version)
                context_display, context_aliases = self._terminology_display_and_aliases(
                    context_name, {"Context", "Scenario"}, attribute_key="context_name"
                )
                context_entities.setdefault(
                    context_id,
                    {
                        "entity_id": context_id,
                        "label": "Context",
                        "standard_name": context_display,
                        "aliases": context_aliases,
                        "kb_version": kb_version,
                        "attributes": {"context_name": context_name},
                    },
                )
                for alias in context_aliases:
                    alias_id = self._alias_id(context_id, alias, kb_version)
                    concept_aliases[alias_id] = {
                        "alias_id": alias_id,
                        "alias_text": alias,
                        "concept_entity_id": context_id,
                        "canonical_name": context_display,
                        "kb_version": kb_version,
                        "status": "draft",
                        "alias_type": "context_alias",
                    }
            for population_name in sorted(draft.not_for_populations):
                population_id = self._entity_id(POPULATION_PREFIX, population_name, kb_version)
                population_display, population_aliases = self._terminology_display_and_aliases(
                    population_name, {"Population"}, attribute_key="population_type"
                )
                population_entities.setdefault(
                    population_id,
                    {
                        "entity_id": population_id,
                        "label": "Population",
                        "standard_name": population_display,
                        "aliases": population_aliases,
                        "kb_version": kb_version,
                        "attributes": {"population_type": population_name},
                    },
                )
                for alias in population_aliases:
                    alias_id = self._alias_id(population_id, alias, kb_version)
                    concept_aliases[alias_id] = {
                        "alias_id": alias_id,
                        "alias_text": alias,
                        "concept_entity_id": population_id,
                        "canonical_name": population_display,
                        "kb_version": kb_version,
                        "status": "draft",
                        "alias_type": "population_alias",
                    }
            for effect_name in sorted(draft.effects):
                effect_id = self._entity_id(EFFECT_PREFIX, effect_name, kb_version)
                effect_entities.setdefault(
                    effect_id,
                    {
                        "entity_id": effect_id,
                        "label": "Effect",
                        "standard_name": effect_name,
                        "aliases": [],
                        "kb_version": kb_version,
                        "attributes": {
                            "effect_name": effect_name,
                            "effect_type": "guideline_effect",
                        },
                    },
                )
            for disease_name in sorted(draft.diseases):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix="disease",
                    value=disease_name,
                    label="Disease",
                    kb_version=kb_version,
                    standard_name=disease_name,
                    aliases=self._terminology_aliases(disease_name, {"Disease"}),
                    attributes={"disease_type": disease_name},
                )
            for symptom_name in sorted(draft.symptoms):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix="symptom",
                    value=symptom_name,
                    label="Symptom",
                    kb_version=kb_version,
                    standard_name=symptom_name,
                    aliases=self._terminology_aliases(symptom_name, {"Symptom"}),
                    attributes={"symptom_type": symptom_name},
                )
            for pattern_name in sorted(draft.patterns):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix="pattern",
                    value=pattern_name,
                    label="Pattern",
                    kb_version=kb_version,
                    standard_name=pattern_name,
                    aliases=self._terminology_aliases(pattern_name, {"Pattern"}),
                    attributes={"pattern_type": pattern_name},
                )
            for pathogenesis_name in sorted(draft.pathogenesis):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=PATHOGENESIS_PREFIX,
                    value=pathogenesis_name,
                    label="Pathogenesis",
                    kb_version=kb_version,
                    aliases=self._terminology_aliases(pathogenesis_name, {"Pathogenesis"}),
                    attributes={"pathogenesis_name": pathogenesis_name},
                )
            for principle_name in sorted(draft.treatment_principles):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=PRINCIPLE_PREFIX,
                    value=principle_name,
                    label="TreatmentPrinciple",
                    kb_version=kb_version,
                    attributes={"principle_name": principle_name},
                )
            for method_name in sorted(draft.treatment_methods):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=METHOD_PREFIX,
                    value=method_name,
                    label="TreatmentMethod",
                    kb_version=kb_version,
                    attributes={"method_name": method_name},
                )
            for usage_method_name in sorted(draft.usage_methods):
                usage_display, usage_aliases = self._terminology_display_and_aliases(
                    usage_method_name, {"UsageMethod"}, attribute_key="usage_method_type"
                )
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=USAGE_PREFIX,
                    value=usage_method_name,
                    label="UsageMethod",
                    kb_version=kb_version,
                    standard_name=usage_display,
                    aliases=usage_aliases,
                    attributes={"usage_method_type": usage_method_name},
                )
            for formula_name in sorted(draft.formulas):
                formula_id = self._entity_id(MATERIAL_PREFIX, formula_name, kb_version)
                ontology_entities.setdefault(
                    formula_id,
                    {
                        "entity_id": formula_id,
                        "label": "Formula",
                        "standard_name": formula_name,
                        "aliases": [],
                        "kb_version": kb_version,
                        "attributes": {
                            "material_type": "formula",
                            "risk_level": "medium",
                            "food_allowed": True,
                            "guide_title": guide_title,
                        },
                    },
                )
            for property_name in sorted(draft.properties):
                property_display, property_aliases = self._terminology_display_and_aliases(
                    property_name, {"Property", "NatureFlavor"}, attribute_key="property_type"
                )
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=PROPERTY_PREFIX,
                    value=property_name,
                    label="Property",
                    kb_version=kb_version,
                    standard_name=property_display,
                    aliases=property_aliases,
                    attributes={
                        "property_type": property_name,
                        "property_category": self._property_category(property_name),
                    },
                )
                if self._property_category(property_name) in {"nature", "flavor"}:
                    self._ensure_tcm_entity(
                        tcm_entities,
                        prefix=NATURE_FLAVOR_PREFIX,
                        value=property_name,
                        label="NatureFlavor",
                        kb_version=kb_version,
                        standard_name=property_display,
                        aliases=property_aliases,
                        attributes={
                            "property_type": property_name,
                            "nature_flavor_category": self._property_category(property_name),
                        },
                    )
            if any(
                self._property_category(property_name) == "five_element"
                for property_name in draft.properties
            ):
                self._ensure_five_element_entities(tcm_entities, kb_version=kb_version)
            for meridian_name in sorted(draft.meridians):
                meridian_system = self._meridian_system(meridian_name)
                meridian_display, meridian_aliases = self._terminology_display_and_aliases(
                    meridian_name, {"Meridian"}, attribute_key="meridian_type"
                )
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=MERIDIAN_PREFIX,
                    value=meridian_name,
                    label="Meridian",
                    kb_version=kb_version,
                    standard_name=meridian_display,
                    aliases=meridian_aliases,
                    attributes={
                        "meridian_type": meridian_name,
                        "meridian_system": meridian_system,
                    },
                )
                self._ensure_meridian_system_entity(
                    tcm_entities,
                    meridian_system=meridian_system,
                    kb_version=kb_version,
                )
                organ_name = MERIDIAN_ORGANS.get(meridian_name)
                if organ_name:
                    self._ensure_tcm_entity(
                        tcm_entities,
                        prefix=PROPERTY_PREFIX,
                        value=organ_name,
                        label="Property",
                        kb_version=kb_version,
                        standard_name=ORGAN_DISPLAY.get(organ_name, organ_name),
                        attributes={
                            "property_type": organ_name,
                            "property_category": "organ",
                        },
                    )
                    self._ensure_tcm_entity(
                        tcm_entities,
                        prefix=ZANGFU_PREFIX,
                        value=organ_name,
                        label="ZangFu",
                        kb_version=kb_version,
                        standard_name=ORGAN_DISPLAY.get(organ_name, organ_name),
                        attributes={
                            "zangfu_type": organ_name,
                            "zangfu_category": "organ",
                        },
                    )
            if any(
                self._meridian_system(meridian_name) == "twelve_primary"
                for meridian_name in draft.meridians
            ):
                self._ensure_twelve_primary_meridian_entities(tcm_entities, kb_version=kb_version)
            for acupoint_name in sorted(draft.acupoints):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=ACUPOINT_PREFIX,
                    value=acupoint_name,
                    label="Acupoint",
                    kb_version=kb_version,
                    attributes={
                        "acupoint_name": acupoint_name,
                        "location_text": draft.acupoint_locations.get(acupoint_name),
                        **self._acupoint_location_attributes(
                            draft.acupoint_locations.get(acupoint_name)
                        ),
                        "method_text": draft.acupoint_methods.get(acupoint_name),
                    },
                )
            for paired_acupoints in draft.acupoint_pairs.values():
                for acupoint_name in sorted(paired_acupoints):
                    self._ensure_tcm_entity(
                        tcm_entities,
                        prefix=ACUPOINT_PREFIX,
                        value=acupoint_name,
                        label="Acupoint",
                        kb_version=kb_version,
                        attributes={"acupoint_name": acupoint_name},
                    )
            for constitution_name in sorted(draft.constitutions):
                constitution_display, constitution_aliases = self._terminology_display_and_aliases(
                    constitution_name, {"Constitution"}, attribute_key="constitution_type"
                )
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=CONSTITUTION_PREFIX,
                    value=constitution_name,
                    label="Constitution",
                    kb_version=kb_version,
                    standard_name=constitution_display,
                    aliases=constitution_aliases,
                    attributes={"constitution_type": constitution_name},
                )
            for season_name in sorted(draft.seasons):
                season_display, season_aliases = self._terminology_display_and_aliases(
                    season_name, {"Season"}, attribute_key="season_type"
                )
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=SEASON_PREFIX,
                    value=season_name,
                    label="Season",
                    kb_version=kb_version,
                    standard_name=season_display,
                    aliases=season_aliases,
                    attributes={"season_type": season_name},
                )
            for stage_name in sorted(draft.stages):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=STAGE_PREFIX,
                    value=stage_name,
                    label="Stage",
                    kb_version=kb_version,
                    attributes={"stage_type": stage_name},
                )
            for dose_value in sorted(draft.doses):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=DOSE_PREFIX,
                    value=dose_value,
                    label="Dose",
                    kb_version=kb_version,
                    attributes=self._dose_attributes(dose_value),
                )
            for role_name in sorted(draft.formula_roles):
                self._ensure_tcm_entity(
                    tcm_entities,
                    prefix=ROLE_PREFIX,
                    value=role_name,
                    label="FormulaRole",
                    kb_version=kb_version,
                    standard_name=FORMULA_ROLE_DISPLAY.get(role_name, role_name),
                    attributes={"formula_role": role_name},
                )

            contraindications = []
            for target_name in sorted(draft.contraindications):
                target_id = self._entity_id(MATERIAL_PREFIX, target_name, kb_version)
                contraindications.append(
                    {
                        "target_entity_id": target_id,
                        "target_name": target_name,
                        "relation": "CONTRAINDICATED_WITH",
                    }
                )
                relationship_count += 1
                assertion_id = self._assertion_id(
                    material_id, "CONTRAINDICATED_WITH", target_id or target_name, kb_version
                )
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": material_id,
                    "predicate_type": "CONTRAINDICATED_WITH",
                    "object_entity_id": target_id,
                    "object_value": target_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title,
                    "evidence_ids": list(material_evidence_ids),
                    "document_id": document_id,
                }
            relationship_count += len(draft.allowed_contexts)
            relationship_count += len(draft.prohibited_contexts)
            relationship_count += len(draft.not_for_populations)
            relationship_count += len(draft.effects)
            relationship_count += len(draft.diseases)
            relationship_count += len(draft.symptoms)
            relationship_count += len(draft.patterns)
            relationship_count += len(draft.pathogenesis)
            relationship_count += len(draft.treatment_principles)
            relationship_count += len(draft.treatment_methods)
            relationship_count += len(draft.usage_methods)
            relationship_count += len(draft.formulas)
            relationship_count += len(draft.properties)
            relationship_count += len(draft.meridians)
            relationship_count += len(draft.acupoints)
            relationship_count += len(draft.constitutions)
            relationship_count += len(draft.seasons)
            relationship_count += len(draft.stages)
            relationship_count += len(draft.doses)
            relationship_count += sum(len(items) for items in draft.formula_roles.values())

            for context_name in sorted(draft.allowed_contexts):
                target_id = self._entity_id(CONTEXT_PREFIX, context_name, kb_version)
                assertion_id = self._assertion_id(
                    material_id, "ALLOWED_IN_CONTEXT", target_id or context_name, kb_version
                )
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": material_id,
                    "predicate_type": "ALLOWED_IN_CONTEXT",
                    "object_entity_id": target_id,
                    "object_value": context_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title,
                    "evidence_ids": list(material_evidence_ids),
                    "document_id": document_id,
                }

            for context_name in sorted(draft.prohibited_contexts):
                target_id = self._entity_id(CONTEXT_PREFIX, context_name, kb_version)
                assertion_id = self._assertion_id(
                    material_id,
                    "PROHIBITED_IN_CONTEXT",
                    target_id or context_name,
                    kb_version,
                )
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": material_id,
                    "predicate_type": "PROHIBITED_IN_CONTEXT",
                    "object_entity_id": target_id,
                    "object_value": context_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title,
                    "evidence_ids": list(material_evidence_ids),
                    "document_id": document_id,
                }

            for population_name in sorted(draft.not_for_populations):
                target_id = self._entity_id(POPULATION_PREFIX, population_name, kb_version)
                assertion_id = self._assertion_id(
                    material_id, "NOT_FOR_POPULATION", target_id or population_name, kb_version
                )
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": material_id,
                    "predicate_type": "NOT_FOR_POPULATION",
                    "object_entity_id": target_id,
                    "object_value": population_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title,
                    "evidence_ids": list(material_evidence_ids),
                    "document_id": document_id,
                }

            for effect_name in sorted(draft.effects):
                target_id = self._entity_id(EFFECT_PREFIX, effect_name, kb_version)
                assertion_id = self._assertion_id(
                    material_id, "HAS_EFFECT", target_id or effect_name, kb_version
                )
                ontology_assertions[assertion_id] = {
                    "assertion_id": assertion_id,
                    "subject_entity_id": material_id,
                    "predicate_type": "HAS_EFFECT",
                    "object_entity_id": target_id,
                    "object_value": effect_name,
                    "kb_version": kb_version,
                    "status": "draft",
                    "source_guide": guide_title,
                    "evidence_ids": list(material_evidence_ids),
                    "document_id": document_id,
                }
            for disease_name in sorted(draft.diseases):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "INDICATED_FOR_DISEASE",
                    self._entity_id("disease", disease_name, kb_version),
                    disease_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
                for symptom_name in sorted(draft.symptoms):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id("disease", disease_name, kb_version),
                        "HAS_SYMPTOM",
                        self._entity_id("symptom", symptom_name, kb_version),
                        symptom_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                for pattern_name in sorted(draft.patterns):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id("disease", disease_name, kb_version),
                        "ASSOCIATED_WITH_PATTERN",
                        self._entity_id("pattern", pattern_name, kb_version),
                        pattern_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
            for symptom_name in sorted(draft.symptoms):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "INDICATED_FOR_SYMPTOM",
                    self._entity_id("symptom", symptom_name, kb_version),
                    symptom_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
                for disease_name in sorted(draft.diseases):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id("symptom", symptom_name, kb_version),
                        "ASSOCIATED_WITH_DISEASE",
                        self._entity_id("disease", disease_name, kb_version),
                        disease_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                for pattern_name in sorted(draft.patterns):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id("pattern", pattern_name, kb_version),
                        "HAS_SYMPTOM",
                        self._entity_id("symptom", symptom_name, kb_version),
                        symptom_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
            for pattern_name in sorted(draft.patterns):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "INDICATED_FOR_PATTERN",
                    self._entity_id("pattern", pattern_name, kb_version),
                    pattern_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
                for disease_name in sorted(draft.diseases):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id("pattern", pattern_name, kb_version),
                        "ASSOCIATED_WITH_DISEASE",
                        self._entity_id("disease", disease_name, kb_version),
                        disease_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )

            for pathogenesis_name in sorted(draft.pathogenesis):
                target_id = self._entity_id(PATHOGENESIS_PREFIX, pathogenesis_name, kb_version)
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "BASED_ON_PATTERN",
                    target_id,
                    pathogenesis_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
            for principle_name in sorted(draft.treatment_principles):
                principle_id = self._entity_id(PRINCIPLE_PREFIX, principle_name, kb_version)
                for syndrome_name in sorted(draft.patterns | draft.pathogenesis):
                    target_prefix = (
                        "pattern" if syndrome_name in draft.patterns else PATHOGENESIS_PREFIX
                    )
                    self._add_assertion(
                        ontology_assertions,
                        principle_id,
                        "BASED_ON_PATTERN",
                        self._entity_id(target_prefix, syndrome_name, kb_version),
                        syndrome_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                for method_name in sorted(draft.treatment_methods):
                    self._add_assertion(
                        ontology_assertions,
                        principle_id,
                        "USES_METHOD",
                        self._entity_id(METHOD_PREFIX, method_name, kb_version),
                        method_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                for formula_name in sorted(
                    draft.formulas or ({material_name} if material_label == "Formula" else set())
                ):
                    self._add_assertion(
                        ontology_assertions,
                        principle_id,
                        "REALIZED_BY_FORMULA",
                        self._entity_id(MATERIAL_PREFIX, formula_name, kb_version),
                        formula_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
            for method_name in sorted(draft.treatment_methods):
                method_id = self._entity_id(METHOD_PREFIX, method_name, kb_version)
                for syndrome_name in sorted(draft.patterns):
                    self._add_assertion(
                        ontology_assertions,
                        method_id,
                        "INDICATED_FOR_PATTERN",
                        self._entity_id("pattern", syndrome_name, kb_version),
                        syndrome_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                for usage_method_name in sorted(draft.usage_methods):
                    self._add_assertion(
                        ontology_assertions,
                        method_id,
                        "HAS_USAGE_METHOD",
                        self._entity_id(USAGE_PREFIX, usage_method_name, kb_version),
                        usage_method_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
            for property_name in sorted(draft.properties):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "HAS_PROPERTY",
                    self._entity_id(PROPERTY_PREFIX, property_name, kb_version),
                    property_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
                if self._property_category(property_name) == "nature":
                    self._add_assertion(
                        ontology_assertions,
                        material_id,
                        "HAS_NATURE",
                        self._entity_id(NATURE_FLAVOR_PREFIX, property_name, kb_version),
                        property_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                elif self._property_category(property_name) == "flavor":
                    self._add_assertion(
                        ontology_assertions,
                        material_id,
                        "HAS_FLAVOR",
                        self._entity_id(NATURE_FLAVOR_PREFIX, property_name, kb_version),
                        property_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
            if any(
                self._property_category(property_name) == "five_element"
                for property_name in draft.properties
            ):
                self._add_five_element_assertions(
                    ontology_assertions,
                    kb_version=kb_version,
                    guide_title=guide_title,
                    evidence_ids=material_evidence_ids,
                    document_id=document_id,
                )
            for meridian_name in sorted(draft.meridians):
                meridian_system = self._meridian_system(meridian_name)
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "ENTERS_MERIDIAN",
                    self._entity_id(MERIDIAN_PREFIX, meridian_name, kb_version),
                    meridian_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
                self._add_assertion(
                    ontology_assertions,
                    self._entity_id(MERIDIAN_PREFIX, meridian_name, kb_version),
                    "BELONGS_TO_MERIDIAN_SYSTEM",
                    self._entity_id(MERIDIAN_SYSTEM_PREFIX, meridian_system, kb_version),
                    meridian_system,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
                organ_name = MERIDIAN_ORGANS.get(meridian_name)
                if organ_name:
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id(MERIDIAN_PREFIX, meridian_name, kb_version),
                        "ASSOCIATED_WITH_ORGAN",
                        self._entity_id(PROPERTY_PREFIX, organ_name, kb_version),
                        organ_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id(MERIDIAN_PREFIX, meridian_name, kb_version),
                        "ASSOCIATED_WITH_ZANGFU",
                        self._entity_id(ZANGFU_PREFIX, organ_name, kb_version),
                        organ_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
            for acupoint_name in sorted(draft.acupoints):
                for meridian_name in sorted(draft.meridians):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id(ACUPOINT_PREFIX, acupoint_name, kb_version),
                        "LOCATED_ON_MERIDIAN",
                        self._entity_id(MERIDIAN_PREFIX, meridian_name, kb_version),
                        meridian_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                for paired_acupoint in sorted(draft.acupoint_pairs.get(acupoint_name, set())):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id(ACUPOINT_PREFIX, acupoint_name, kb_version),
                        "COMBINES_WITH",
                        self._entity_id(ACUPOINT_PREFIX, paired_acupoint, kb_version),
                        paired_acupoint,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                for symptom_name in sorted(draft.symptoms):
                    self._add_assertion(
                        ontology_assertions,
                        self._entity_id(ACUPOINT_PREFIX, acupoint_name, kb_version),
                        "INDICATED_FOR_SYMPTOM",
                        self._entity_id("symptom", symptom_name, kb_version),
                        symptom_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
            if draft.acupoints:
                for meridian_name in sorted(draft.meridians):
                    for symptom_name in sorted(draft.symptoms):
                        self._add_assertion(
                            ontology_assertions,
                            self._entity_id(MERIDIAN_PREFIX, meridian_name, kb_version),
                            "MANIFESTS_AS_SYMPTOM",
                            self._entity_id("symptom", symptom_name, kb_version),
                            symptom_name,
                            kb_version,
                            guide_title,
                            material_evidence_ids,
                            document_id,
                        )
            if any(
                self._meridian_system(meridian_name) == "twelve_primary"
                for meridian_name in draft.meridians
            ):
                self._add_twelve_primary_meridian_flow_assertions(
                    ontology_assertions,
                    kb_version=kb_version,
                    guide_title=guide_title,
                    evidence_ids=material_evidence_ids,
                    document_id=document_id,
                )
            for constitution_name in sorted(draft.constitutions):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "SUITABLE_FOR_CONSTITUTION",
                    self._entity_id(CONSTITUTION_PREFIX, constitution_name, kb_version),
                    constitution_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
            for season_name in sorted(draft.seasons):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "SEASONAL_RELEVANCE",
                    self._entity_id(SEASON_PREFIX, season_name, kb_version),
                    season_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
            for stage_name in sorted(draft.stages):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "SUITABLE_FOR_STAGE",
                    self._entity_id(STAGE_PREFIX, stage_name, kb_version),
                    stage_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
            for dose_value in sorted(draft.doses):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "HAS_DOSE",
                    self._entity_id(DOSE_PREFIX, dose_value, kb_version),
                    dose_value,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
            for usage_method_name in sorted(draft.usage_methods):
                self._add_assertion(
                    ontology_assertions,
                    material_id,
                    "HAS_USAGE_METHOD",
                    self._entity_id(USAGE_PREFIX, usage_method_name, kb_version),
                    usage_method_name,
                    kb_version,
                    guide_title,
                    material_evidence_ids,
                    document_id,
                )
            for role_name, herbs in sorted(draft.formula_roles.items()):
                role_id = self._entity_id(ROLE_PREFIX, role_name, kb_version)
                for herb_name in sorted(herbs):
                    herb_id = self._entity_id(MATERIAL_PREFIX, herb_name, kb_version)
                    ontology_entities.setdefault(
                        herb_id,
                        {
                            "entity_id": herb_id,
                            "label": self._material_label(herb_name),
                            "standard_name": herb_name,
                            "aliases": [],
                            "kb_version": kb_version,
                            "attributes": {
                                "material_type": self._material_label(herb_name).lower(),
                                "risk_level": "medium",
                                "food_allowed": True,
                                "guide_title": guide_title,
                            },
                        },
                    )
                    self._add_assertion(
                        ontology_assertions,
                        material_id,
                        "HAS_INGREDIENT",
                        herb_id,
                        herb_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                    self._add_assertion(
                        ontology_assertions,
                        herb_id,
                        "HAS_FORMULA_ROLE",
                        role_id,
                        role_name,
                        kb_version,
                        guide_title,
                        material_evidence_ids,
                        document_id,
                    )
                    condition_set_id = self._formula_role_condition_set_id(
                        material_id, herb_id, role_id, kb_version
                    )
                    condition_sets[condition_set_id] = {
                        "condition_set_id": condition_set_id,
                        "logic": {
                            "all": [
                                {
                                    "type": "formula",
                                    "operator": "equals",
                                    "value": material_name,
                                    "value_type": "concept",
                                    "normalized_concept_id": material_id,
                                    "scope_note": "限定该药物角色仅在当前方剂中成立",
                                }
                            ]
                        },
                        "note": "方剂角色上下文条件",
                    }
                    role_assertion_id = self._assertion_id(
                        herb_id, "HAS_FORMULA_ROLE", role_id, kb_version
                    )
                    if role_assertion_id in ontology_assertions:
                        ontology_assertions[role_assertion_id]["condition_set_id"] = (
                            condition_set_id
                        )

            knowledge_cards[material_id] = {
                "entity": {
                    "entity_id": material_id,
                    "standard_name": material_name,
                    "label": material_label,
                    "risk_level": risk_level,
                },
                "aliases": sorted(draft.aliases),
                "effects": sorted(draft.effects),
                "diseases": sorted(draft.diseases),
                "symptoms": sorted(draft.symptoms),
                "patterns": sorted(draft.patterns),
                "treatment_methods": sorted(draft.treatment_methods),
                "usage_methods": sorted(draft.usage_methods),
                "not_for_populations": sorted(draft.not_for_populations),
                "allowed_contexts": sorted(draft.allowed_contexts),
                "prohibited_contexts": sorted(draft.prohibited_contexts),
                "contraindications": contraindications,
                "kb_version": kb_version,
                "source_guide": guide_title,
                "evidence": draft.evidence[:10],
                "assertion_count": sum(
                    1 for a in ontology_assertions.values() if a["subject_entity_id"] == material_id
                ),
                "evidence_count": len(material_evidence_ids),
                "derived_from_assertions": True,
            }

        ontology_entities.update(context_entities)
        ontology_entities.update(population_entities)
        ontology_entities.update(effect_entities)
        ontology_entities.update(tcm_entities)
        ontology_assertions, validation_warnings = self._validate_assertions(
            ontology_entities,
            ontology_assertions,
        )
        merged_warnings.extend(validation_warnings)
        mentions, normalization_decisions = self._build_import_normalization_assets(
            guide_text=guide_text,
            ontology_entities=ontology_entities,
            unresolved_terms=self._collect_unresolved_terms(drafts),
            kb_version=kb_version,
        )

        return GuidelineOntologyBundle(
            ontology_entities=ontology_entities,
            knowledge_cards=knowledge_cards,
            ontology_assertions=ontology_assertions,
            evidence_sources=evidence_sources,
            concept_aliases=concept_aliases,
            guideline_documents=guideline_documents,
            mentions=mentions,
            normalization_decisions=normalization_decisions,
            condition_sets=condition_sets,
            warnings=merged_warnings,
            extracted_materials=material_names,
            relationship_count=relationship_count,
            extractor_engine=extractor_engine,
            extractor_model=extractor_model,
            extractor_prompt_version=extractor_prompt_version,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            extraction_stats=self._build_extraction_stats(
                guide_text=guide_text,
                material_names=material_names,
                relationship_count=relationship_count,
                knowledge_card_count=len(knowledge_cards),
                warning_count=len(merged_warnings),
                source_kind=extractor_engine,
            ),
        )

    def _build_extraction_stats(
        self,
        *,
        guide_text: str,
        material_names: list[str],
        relationship_count: int,
        knowledge_card_count: int,
        warning_count: int,
        source_kind: str,
    ) -> dict[str, Any]:
        text = guide_text or ""
        return {
            "source_kind": source_kind,
            "input_char_count": len(text),
            "input_line_count": len([line for line in text.splitlines() if line.strip()]),
            "material_count": len(material_names),
            "knowledge_card_count": knowledge_card_count,
            "relationship_count": relationship_count,
            "warning_count": warning_count,
            "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        }

    def _decode_text_bytes(self, raw: bytes) -> tuple[str, str]:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                return raw.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore"), "utf-8(ignore-errors)"

    def _extract_docx_text(self, raw: bytes) -> str:
        try:
            with zipfile.ZipFile(BytesIO(raw)) as archive:
                xml_bytes = archive.read("word/document.xml")
        except Exception as exc:
            raise ValueError("Failed to parse docx file") from exc
        root = ElementTree.fromstring(xml_bytes)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for paragraph in root.findall(".//w:p", namespace):
            parts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
            line = "".join(parts).strip()
            if line:
                paragraphs.append(line)
        return "\n".join(paragraphs)

    def _extract_pdf_text(self, raw: bytes) -> tuple[str, list[str]]:
        if PdfReader is None:
            raise ValueError("PDF support requires the pypdf package to be installed")

        try:
            reader = PdfReader(BytesIO(raw))
        except Exception as exc:
            raise ValueError("Failed to parse pdf file") from exc

        warnings: list[str] = []
        pages: list[str] = []
        for index, page in enumerate(reader.pages, start=1):
            try:
                page_text = (page.extract_text() or "").strip()
            except Exception as exc:
                warnings.append(f"第 {index} 页解析失败: {exc}")
                continue
            if page_text:
                pages.append(page_text)

        text = "\n\n".join(pages).strip()
        if not text:
            warnings.append("PDF 未提取到可用文本，可能是扫描件或图片型 PDF。")
        return text, warnings

    def _normalize_text(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").replace("（", "(").replace("）", ")")

    def _collect_material_candidates(self, text: str) -> list[str]:
        candidates: set[str] = set()
        for line in text.splitlines():
            stripped = line.strip()
            section_name = self._extract_section_material_name(stripped)
            if section_name:
                candidates.add(section_name)
            inferred = self._extract_leading_material_candidate(stripped)
            if inferred:
                candidates.add(inferred)
            for target in self._extract_contra_target_candidates(stripped):
                candidates.add(target)
        return sorted(candidates)

    def _extract_leading_material_candidate(self, text: str) -> str | None:
        patterns = [
            r"^(?:[一二三四五六七八九十0-9]+[、.．]\s*)?([\u4e00-\u9fff]{1,12})(?=(?:\(|（|[:：]|可用于|适用于|禁用于|不宜用于|慎用于|功效|主治|适应证|适应症))",
            r"(?:^|[\n，,；;])([\u4e00-\u9fff]{1,12})(?=(?:可用于|适用于|禁用于|不宜用于|慎用于|功效[:：]|主治[:：]|适应证[:：]|适应症[:：]))",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                cleaned = self._clean_candidate_name(match.group(1))
                if cleaned:
                    return cleaned
        return None

    def _extract_contra_target_candidates(self, text: str) -> set[str]:
        candidates: set[str] = set()
        patterns = [
            r"(?:不宜与|禁与|避免与)([\u4e00-\u9fff]{1,12})同(?:用|服)",
            r"(?:与|和)([\u4e00-\u9fff]{1,12})(?:配伍禁忌|不宜同用|不宜同服|同用禁忌)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                cleaned = self._clean_candidate_name(match.group(1))
                if cleaned:
                    candidates.add(cleaned)
        return candidates

    def _extract_section_material_name(self, line: str) -> str | None:
        if not line or not any(hint in line for hint in (*MATERIAL_HINTS, *TCM_FIELD_HINTS)):
            return None
        patterns = [
            r"^(?:[一二三四五六七八九十0-9]+[、.．]\s*)?([\u4e00-\u9fff]{1,12})[:：]",
            r"^【([\u4e00-\u9fff]{1,12})】",
            r"^([\u4e00-\u9fff]{1,12})\s*\((?:别名|又名)",
        ]
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                cleaned = self._clean_candidate_name(match.group(1))
                if cleaned:
                    return cleaned
        return None

    def _clean_candidate_name(self, value: str) -> str | None:
        value = value.strip().strip("，,。：:；;()[]【】")
        value = re.sub(r"^[但并且及或与和]\s*", "", value)
        value = re.sub(r"\s*[与和及或]$", "", value)
        if not value or len(value) > 12 or value in STOPWORDS:
            return None
        if any(token in value for token in ("功效", "主治", "适应", "禁用于", "适用于", "别名")):
            return None
        if any(char in value for char in "指南共识建议推荐") and len(value) > 4:
            return None
        return value

    def _infer_primary_material(
        self, clause: str, material_names: list[str], current_material: str | None
    ) -> str | None:
        hits = [name for name in material_names if name and name in clause]
        if hits:
            hits.sort(key=len, reverse=True)
            return hits[0]
        return current_material if current_material in material_names else None

    def _extract_aliases(self, clause: str, material_name: str) -> set[str]:
        aliases: set[str] = set()
        patterns = [
            rf"{re.escape(material_name)}\s*\((?:别名|又名)[:：]?([^()（）]+)\)",
            r"(?:别名|又名)[:：]\s*([\u4e00-\u9fff、，,\s]{1,24})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, clause):
                aliases.update(self._split_text_values(match.group(1), max_length=24))
        aliases.discard(material_name)
        return aliases

    def _extract_effects(self, clause: str) -> set[str]:
        match = re.search(r"(?:功效|主治|适应证|适应症)[:：]\s*([^。；;]+)", clause)
        return set(self._split_text_values(match.group(1), max_length=32)) if match else set()

    def _extract_tcm_core_fields(self, clause: str, draft: MaterialDraft) -> None:
        field_map = {
            "diseases": (r"(?:疾病|病名)[:：]\s*([^。；;]+)", draft.diseases, 32),
            "symptoms": (r"(?:症状|症见)[:：]\s*([^。；;]+)", draft.symptoms, 32),
            "patterns": (r"(?:辨证|证候分型|证型分类)[:：]\s*([^。；;]+)", draft.patterns, 32),
            "syndromes": (r"(?:证候|证型)[:：]\s*([^。；;]+)", draft.patterns, 32),
            "pathogenesis": (r"病机[:：]\s*([^。；;]+)", draft.pathogenesis, 32),
            "principles": (r"治则[:：]\s*([^。；;]+)", draft.treatment_principles, 32),
            "methods": (r"治法[:：]\s*([^。；;]+)", draft.treatment_methods, 32),
            "usage_methods": (r"用法[:：]\s*([^。；;]+)", draft.usage_methods, 24),
            "formulas": (r"方剂[:：]\s*([^。；;]+)", draft.formulas, 24),
            "acupoints": (r"(?:腧穴|穴位)[:：]\s*([^。；;]+)", draft.acupoints, 24),
            "stages": (r"(?:阶段|分期)[:：]\s*([^。；;]+)", draft.stages, 24),
            "doses": (r"(?:剂量|用量)[:：]\s*([^。；;]+)", draft.doses, 24),
        }
        for _, (pattern, target, max_length) in field_map.items():
            match = re.search(pattern, clause)
            if match:
                values = self._split_text_values(match.group(1), max_length=max_length)
                if target is draft.diseases:
                    self._add_canonical_or_unresolved(
                        draft, "disease", values, self._canonicalize_disease, target
                    )
                elif target is draft.symptoms:
                    self._add_canonical_or_unresolved(
                        draft, "symptom", values, self._canonicalize_symptom, target
                    )
                elif target is draft.patterns:
                    self._add_canonical_or_unresolved(
                        draft, "pattern", values, self._canonicalize_pattern, target
                    )
                elif target is draft.pathogenesis:
                    self._add_canonical_or_unresolved(
                        draft, "pathogenesis", values, self._canonicalize_pathogenesis, target
                    )
                elif target is draft.usage_methods:
                    self._add_canonical_or_unresolved(
                        draft, "usage_method", values, self._canonicalize_usage_method, target
                    )
                else:
                    target.update(values)

        location_match = re.search(r"定位[:：]\s*([^。；;]+)", clause)
        if location_match and draft.acupoints:
            location_text = self._clean_text_value(location_match.group(1), max_length=80)
            if location_text:
                for acupoint_name in draft.acupoints:
                    draft.acupoint_locations[acupoint_name] = location_text
        method_match = re.search(r"手法[:：]\s*([^。；;]+)", clause)
        if method_match and draft.acupoints:
            method_text = self._clean_text_value(method_match.group(1), max_length=80)
            if method_text:
                for acupoint_name in draft.acupoints:
                    draft.acupoint_methods[acupoint_name] = method_text
        pair_match = re.search(r"(?:配穴|配伍)[:：]\s*([^。；;]+)", clause)
        if pair_match and draft.acupoints:
            paired = set(self._split_text_values(pair_match.group(1), max_length=24))
            for acupoint_name in draft.acupoints:
                draft.acupoint_pairs.setdefault(acupoint_name, set()).update(
                    item for item in paired if item != acupoint_name
                )

        property_match = re.search(r"性味[:：]\s*([^。；;]+)", clause)
        if property_match:
            for item in self._split_text_values(property_match.group(1), max_length=16):
                canonical = self._canonicalize_property(item)
                if canonical:
                    draft.properties.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("property", set()).add(item)
        else:
            draft.properties.update(
                self._extract_terminology_hits(
                    clause, {"Property", "NatureFlavor"}, attribute_key="property_type"
                )
            )

        draft.diseases.update(self._extract_terminology_hits(clause, {"Disease"}))
        draft.symptoms.update(self._extract_terminology_hits(clause, {"Symptom"}))
        draft.patterns.update(self._extract_terminology_hits(clause, {"Pattern"}))
        draft.pathogenesis.update(self._extract_terminology_hits(clause, {"Pathogenesis"}))
        draft.usage_methods.update(
            self._extract_terminology_hits(clause, {"UsageMethod"}, attribute_key="usage_method_type")
        )

        meridian_match = re.search(r"归经[:：]\s*([^。；;]+)", clause)
        if meridian_match:
            for item in self._split_text_values(meridian_match.group(1), max_length=16):
                canonical = self._canonicalize_meridian(item)
                if canonical:
                    draft.meridians.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("meridian", set()).add(item)

        constitution_match = re.search(r"体质[:：]\s*([^。；;]+)", clause)
        if constitution_match:
            for item in self._split_text_values(constitution_match.group(1), max_length=16):
                canonical = self._canonicalize_constitution(item)
                if canonical:
                    draft.constitutions.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("constitution", set()).add(item)

        season_match = re.search(r"(?:时令|季节)[:：]\s*([^。；;]+)", clause)
        if season_match:
            for item in self._split_text_values(season_match.group(1), max_length=16):
                canonical = self._canonicalize_season(item)
                if canonical:
                    draft.seasons.add(canonical)
                else:
                    draft.unresolved_terms.setdefault("season", set()).add(item)

        for role_name, role_label in {
            "monarch": "君药",
            "minister": "臣药",
            "assistant": "佐药",
            "courier": "使药",
        }.items():
            match = re.search(rf"{role_label}[:：]\s*([^。；;]+)", clause)
            if match:
                draft.formula_roles.setdefault(role_name, set()).update(
                    self._split_text_values(match.group(1), max_length=24)
                )

    def _extract_populations(self, clause: str) -> set[str]:
        return self._extract_terminology_hits(clause, {"Population"}, attribute_key="population_type")

    def _extract_contexts(self, clause: str) -> set[str]:
        return self._extract_terminology_hits(clause, {"Context", "Scenario"}, attribute_key="context_name")

    def _has_negative_cue(self, clause: str) -> bool:
        return any(
            token in clause
            for token in ("禁用于", "不宜用于", "慎用于", "不宜与", "禁与", "避免与")
        )

    def _has_positive_context_cue(self, clause: str) -> bool:
        return any(token in clause for token in ("可用于", "适用于"))

    def _extract_contraindications(
        self, clause: str, material_name: str, material_names: list[str]
    ) -> set[str]:
        targets = self._extract_contra_target_candidates(clause)
        targets.discard(material_name)
        return {target for target in targets if target in material_names or target}

    def _extract_contraindication_names(self, value: Any) -> list[str]:
        names: list[str] = []
        if value is None:
            return names
        if isinstance(value, str):
            return self._split_text_values(value, max_length=24)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    candidate = item.get("target_name") or item.get("name") or item.get("target")
                    if candidate:
                        names.extend(self._split_text_values(str(candidate), max_length=24))
                else:
                    names.extend(self._extract_contraindication_names(item))
        return names

    def _add_canonical_or_unresolved(
        self,
        draft: MaterialDraft,
        term_type: str,
        values: list[str],
        canonicalizer: Any,
        target: set[str],
    ) -> None:
        for item in values:
            canonical = canonicalizer(item)
            if canonical:
                target.add(canonical)
            else:
                draft.unresolved_terms.setdefault(term_type, set()).add(item)

    def _normalize_string_values(self, value: Any, *, split_inline: bool = True) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return (
                self._split_text_values(value, max_length=64)
                if split_inline
                else ([value.strip()] if value.strip() else [])
            )
        if isinstance(value, list):
            items: list[str] = []
            for item in value:
                items.extend(self._normalize_string_values(item, split_inline=split_inline))
            return items
        return [str(value)]

    def _split_text_values(self, value: str, *, max_length: int) -> list[str]:
        result: list[str] = []
        for part in re.split(r"[、，,；;\s]+", value):
            cleaned = self._clean_text_value(part, max_length=max_length)
            if cleaned and cleaned not in result:
                result.append(cleaned)
        return result

    def _clean_text_value(self, value: str, *, max_length: int) -> str | None:
        cleaned = value.strip().strip("，,。：:；;()[]【】")
        if not cleaned or len(cleaned) > max_length:
            return None
        return cleaned

    def _canonicalize_context(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Context", "Scenario"}, attribute_key="context_name")

    def _canonicalize_population(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Population"}, attribute_key="population_type")

    def _canonicalize_property(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Property", "NatureFlavor"}, attribute_key="property_type")

    def _property_category(self, property_name: str) -> str:
        if property_name in {"warm", "cool", "cold", "heat", "温", "凉", "寒", "热"}:
            return "nature"
        if property_name in {"sweet", "bitter", "acrid", "sour", "salty", "甘", "苦", "辛", "酸", "咸"}:
            return "flavor"
        if property_name in {"yin", "yang", "阴", "阳"}:
            return "yin_yang"
        if property_name in {"wood", "fire", "earth", "metal", "water", "木", "火", "土", "金", "水"}:
            return "five_element"
        return "theory_property"

    def _meridian_system(self, meridian_name: str) -> str:
        return (
            "extraordinary_vessel" if meridian_name in EXTRAORDINARY_VESSELS else "twelve_primary"
        )

    def _ensure_meridian_system_entity(
        self,
        entities: dict[str, dict[str, Any]],
        *,
        meridian_system: str,
        kb_version: str,
    ) -> None:
        self._ensure_tcm_entity(
            entities,
            prefix=MERIDIAN_SYSTEM_PREFIX,
            value=meridian_system,
            label="MeridianSystem",
            kb_version=kb_version,
            standard_name=MERIDIAN_SYSTEM_DISPLAY.get(meridian_system, meridian_system),
            attributes={"meridian_system_type": meridian_system},
        )

    def _ensure_twelve_primary_meridian_entities(
        self, entities: dict[str, dict[str, Any]], *, kb_version: str
    ) -> None:
        for meridian_name in TWELVE_PRIMARY_MERIDIAN_FLOW:
            meridian_display, meridian_aliases = self._terminology_display_and_aliases(
                meridian_name, {"Meridian"}, attribute_key="meridian_type"
            )
            self._ensure_tcm_entity(
                entities,
                prefix=MERIDIAN_PREFIX,
                value=meridian_name,
                label="Meridian",
                kb_version=kb_version,
                standard_name=meridian_display,
                aliases=meridian_aliases,
                attributes={
                    "meridian_type": meridian_name,
                    "meridian_system": "twelve_primary",
                },
            )

    def _canonicalize_disease(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Disease"})

    def _canonicalize_symptom(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Symptom"})

    def _canonicalize_pattern(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Pattern"})

    def _canonicalize_pathogenesis(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Pathogenesis"})

    def _canonicalize_terminology(
        self, value: str, concept_types: set[str], *, attribute_key: str | None = None
    ) -> str | None:
        matches = self.terminology_resolver.resolve(value, concept_types=concept_types)
        if not matches:
            return None
        if attribute_key:
            attribute_values = {
                str(match.attributes.get(attribute_key) or "").strip()
                for match in matches
                if str(match.attributes.get(attribute_key) or "").strip()
            }
            if len(attribute_values) == 1:
                return next(iter(attribute_values))
        standard_names = {match.standard_name for match in matches if match.standard_name}
        if len(standard_names) == 1:
            return next(iter(standard_names))
        return None

    def _terminology_aliases(self, standard_name: str, concept_types: set[str]) -> list[str]:
        aliases: list[str] = []
        for match in self.terminology_resolver.resolve(standard_name, concept_types=concept_types):
            if match.standard_name != standard_name:
                continue
            for alias in match.aliases:
                if alias and alias != standard_name and alias not in aliases:
                    aliases.append(alias)
        return sorted(aliases)

    def _terminology_display_and_aliases(
        self,
        value: str,
        concept_types: set[str],
        *,
        attribute_key: str | None = None,
    ) -> tuple[str, list[str]]:
        if attribute_key:
            matches = self.terminology_resolver.resolve_by_attribute(
                attribute_key,
                value,
                concept_types=concept_types,
            )
        else:
            matches = self.terminology_resolver.resolve(value, concept_types=concept_types)
        if not matches:
            return value, []
        standard_names = sorted({match.standard_name for match in matches if match.standard_name})
        display_name = standard_names[0] if standard_names else value
        aliases: list[str] = []
        for match in matches:
            if match.standard_name != display_name:
                continue
            for alias in match.aliases:
                if alias and alias != display_name and alias not in aliases:
                    aliases.append(alias)
        return display_name, sorted(aliases)

    def _extract_terminology_hits(
        self, text: str, concept_types: set[str], *, attribute_key: str | None = None
    ) -> set[str]:
        values: set[str] = set()
        for item in self.terminology_resolver.find_mentions(text, concept_types=concept_types):
            if attribute_key:
                attribute_value = str(item.attributes.get(attribute_key) or "").strip()
                if attribute_value:
                    values.add(attribute_value)
                    continue
            values.add(item.standard_name)
        return values

    def _canonicalize_usage_method(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"UsageMethod"}, attribute_key="usage_method_type")

    def _canonicalize_meridian(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Meridian"}, attribute_key="meridian_type")

    def _canonicalize_constitution(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Constitution"}, attribute_key="constitution_type")

    def _canonicalize_season(self, value: str) -> str | None:
        return self._canonicalize_terminology(value, {"Season"}, attribute_key="season_type")

    def _merge_formula_roles(self, draft: MaterialDraft, value: Any) -> None:
        if not isinstance(value, dict):
            return
        alias_to_role = {
            "monarch": "monarch",
            "君药": "monarch",
            "minister": "minister",
            "臣药": "minister",
            "assistant": "assistant",
            "佐药": "assistant",
            "courier": "courier",
            "使药": "courier",
        }
        for raw_role, herbs in value.items():
            role = alias_to_role.get(str(raw_role))
            if not role:
                continue
            draft.formula_roles.setdefault(role, set()).update(self._normalize_string_values(herbs))

    def _ensure_tcm_entity(
        self,
        entities: dict[str, dict[str, Any]],
        *,
        prefix: str,
        value: str,
        label: str,
        kb_version: str,
        attributes: dict[str, Any],
        standard_name: str | None = None,
        aliases: list[str] | None = None,
    ) -> str:
        entity_id = self._entity_id(prefix, value, kb_version)
        entities.setdefault(
            entity_id,
            {
                "entity_id": entity_id,
                "label": label,
                "standard_name": standard_name or value,
                "aliases": sorted(set(aliases or [])),
                "kb_version": kb_version,
                "attributes": attributes,
            },
        )
        return entity_id

    def _ensure_five_element_entities(
        self, entities: dict[str, dict[str, Any]], *, kb_version: str
    ) -> None:
        for element_name in sorted(FIVE_ELEMENT_GENERATES):
            element_display, element_aliases = self._terminology_display_and_aliases(
                element_name, {"Property", "NatureFlavor"}, attribute_key="property_type"
            )
            self._ensure_tcm_entity(
                entities,
                prefix=PROPERTY_PREFIX,
                value=element_name,
                label="Property",
                kb_version=kb_version,
                standard_name=element_display,
                aliases=element_aliases,
                attributes={
                    "property_type": element_name,
                    "property_category": "five_element",
                },
            )

    def _add_five_element_assertions(
        self,
        ontology_assertions: dict[str, dict[str, Any]],
        *,
        kb_version: str,
        guide_title: str,
        evidence_ids: list[str],
        document_id: str,
    ) -> None:
        for source, target in FIVE_ELEMENT_GENERATES.items():
            self._add_assertion(
                ontology_assertions,
                self._entity_id(PROPERTY_PREFIX, source, kb_version),
                "GENERATES",
                self._entity_id(PROPERTY_PREFIX, target, kb_version),
                target,
                kb_version,
                guide_title,
                evidence_ids,
                document_id,
            )
        for source, target in FIVE_ELEMENT_RESTRICTS.items():
            self._add_assertion(
                ontology_assertions,
                self._entity_id(PROPERTY_PREFIX, source, kb_version),
                "RESTRICTS",
                self._entity_id(PROPERTY_PREFIX, target, kb_version),
                target,
                kb_version,
                guide_title,
                evidence_ids,
                document_id,
            )
            self._add_assertion(
                ontology_assertions,
                self._entity_id(PROPERTY_PREFIX, source, kb_version),
                "OVERACTS",
                self._entity_id(PROPERTY_PREFIX, target, kb_version),
                target,
                kb_version,
                guide_title,
                evidence_ids,
                document_id,
            )
            self._add_assertion(
                ontology_assertions,
                self._entity_id(PROPERTY_PREFIX, target, kb_version),
                "INSULTS",
                self._entity_id(PROPERTY_PREFIX, source, kb_version),
                source,
                kb_version,
                guide_title,
                evidence_ids,
                document_id,
            )

    def _add_twelve_primary_meridian_flow_assertions(
        self,
        ontology_assertions: dict[str, dict[str, Any]],
        *,
        kb_version: str,
        guide_title: str,
        evidence_ids: list[str],
        document_id: str,
    ) -> None:
        flow = TWELVE_PRIMARY_MERIDIAN_FLOW
        for index, source in enumerate(flow):
            target = flow[(index + 1) % len(flow)]
            self._add_assertion(
                ontology_assertions,
                self._entity_id(MERIDIAN_PREFIX, source, kb_version),
                "FLOWS_TO",
                self._entity_id(MERIDIAN_PREFIX, target, kb_version),
                target,
                kb_version,
                guide_title,
                evidence_ids,
                document_id,
            )

    def _add_assertion(
        self,
        ontology_assertions: dict[str, dict[str, Any]],
        subject_id: str,
        predicate_type: str,
        object_entity_id: str | None,
        object_value: str,
        kb_version: str,
        guide_title: str,
        evidence_ids: list[str],
        document_id: str,
    ) -> None:
        predicate_type = canonical_relation_code(predicate_type)
        assertion_id = self._assertion_id(
            subject_id, predicate_type, object_entity_id or object_value, kb_version
        )
        ontology_assertions[assertion_id] = {
            "assertion_id": assertion_id,
            "subject_entity_id": subject_id,
            "predicate_type": predicate_type,
            "object_entity_id": object_entity_id,
            "object_value": object_value,
            "kb_version": kb_version,
            "status": "draft",
            "source_guide": guide_title,
            "evidence_ids": list(evidence_ids),
            "document_id": document_id,
        }

    def _entity_id(self, prefix: str, value: str, kb_version: str | None = None) -> str:
        base = f"{value}::{kb_version}" if kb_version else value
        return f"{prefix}_{hashlib.md5(base.encode('utf-8')).hexdigest()[:12]}"

    def _assertion_id(
        self, subject_id: str, predicate_type: str, object_key: str, kb_version: str
    ) -> str:
        raw = f"{subject_id}|{predicate_type}|{object_key}|{kb_version}"
        return f"assert_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]}"

    def _evidence_id(self, entity_id: str, ordinal: int, kb_version: str) -> str:
        raw = f"{entity_id}|{ordinal}|{kb_version}"
        return f"evidence_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]}"

    def _alias_id(self, entity_id: str, alias_text: str, kb_version: str) -> str:
        raw = f"{entity_id}|{alias_text}|{kb_version}"
        return f"alias_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]}"

    def _document_id(self, guide_title: str, kb_version: str) -> str:
        raw = f"{guide_title}|{kb_version}"
        return f"guide_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]}"

    def _formula_role_condition_set_id(
        self, formula_id: str, herb_id: str, role_id: str, kb_version: str
    ) -> str:
        raw = f"{formula_id}|{herb_id}|{role_id}|{kb_version}"
        return f"cond_formula_role_{hashlib.md5(raw.encode('utf-8')).hexdigest()[:16]}"

    def _build_import_normalization_assets(
        self,
        *,
        guide_text: str,
        ontology_entities: dict[str, dict[str, Any]],
        unresolved_terms: dict[str, set[str]] | None = None,
        kb_version: str,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        mentions: dict[str, dict[str, Any]] = {}
        decisions: dict[str, dict[str, Any]] = {}
        created_at = datetime.now(timezone.utc)
        candidates_by_mention: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
        for entity in ontology_entities.values():
            entity_id = str(entity.get("entity_id") or "")
            canonical_name = str(entity.get("standard_name") or "")
            label = str(entity.get("label") or "Entity")
            terms = [canonical_name, *[str(alias) for alias in (entity.get("aliases") or [])]]
            for term in sorted({item for item in terms if item}, key=len, reverse=True):
                start = guide_text.find(term)
                if start < 0:
                    continue
                end = start + len(term)
                raw_mention = f"{kb_version}|{term}|{start}|{end}"
                mention_id = f"mention_{hashlib.md5(raw_mention.encode('utf-8')).hexdigest()[:16]}"
                mentions[mention_id] = {
                    "mention_id": mention_id,
                    "source_type": "guideline_import",
                    "source_record_id": kb_version,
                    "surface_text": term,
                    "normalized_text": term.strip(),
                    "start_offset": start,
                    "end_offset": end,
                    "mention_type_guess": label.lower(),
                    "context_window": guide_text[
                        max(0, start - 30) : min(len(guide_text), end + 30)
                    ],
                    "kb_version": kb_version,
                    "created_at": created_at,
                }
                candidate = {
                    "concept_id": entity_id,
                    "canonical_name": canonical_name,
                    "concept_type": label,
                    "score": 1.0 if term == canonical_name else 0.92,
                }
                candidates_by_mention.setdefault((mention_id, start, end), []).append(candidate)
        for resolved in self.terminology_resolver.find_mentions(
            guide_text,
            concept_types={"Disease", "Symptom", "Pattern", "Pathogenesis", "Constitution"},
            min_length=2,
        ):
            term = resolved.surface_text
            start = guide_text.find(term)
            if start < 0:
                continue
            end = start + len(term)
            raw_mention = f"{kb_version}|terminology|{term}|{start}|{end}"
            mention_id = f"mention_{hashlib.md5(raw_mention.encode('utf-8')).hexdigest()[:16]}"
            mentions.setdefault(
                mention_id,
                {
                    "mention_id": mention_id,
                    "source_type": "guideline_import",
                    "source_record_id": kb_version,
                    "surface_text": term,
                    "normalized_text": term.strip(),
                    "start_offset": start,
                    "end_offset": end,
                    "mention_type_guess": resolved.concept_type.lower(),
                    "context_window": guide_text[max(0, start - 30): min(len(guide_text), end + 30)],
                    "kb_version": kb_version,
                    "created_at": created_at,
                },
            )
            candidates_by_mention.setdefault((mention_id, start, end), []).append(
                {
                    "concept_id": resolved.concept_id,
                    "canonical_name": resolved.standard_name,
                    "concept_type": resolved.concept_type,
                    "score": resolved.score,
                    "terminology_source": resolved.source,
                    "alias_id": resolved.alias_id,
                }
            )
        for (mention_id, _, _), candidates in candidates_by_mention.items():
            unique_candidates = {
                str(candidate["concept_id"]): candidate for candidate in candidates
            }
            candidate_list = sorted(
                unique_candidates.values(),
                key=lambda item: (
                    -float(item.get("score", 0.0)),
                    str(item.get("concept_type", "")),
                    str(item.get("canonical_name", "")),
                ),
            )
            is_ambiguous = len(candidate_list) > 1
            chosen = candidate_list[0] if candidate_list else {}
            decision_id = (
                f"normdec_{hashlib.md5((mention_id + 'import').encode('utf-8')).hexdigest()[:16]}"
            )
            decisions[decision_id] = {
                "decision_id": decision_id,
                "mention_id": mention_id,
                "resolved_concept_id": None if is_ambiguous else chosen.get("concept_id"),
                "canonical_name": None if is_ambiguous else chosen.get("canonical_name"),
                "resolver_type": "guideline_import_alias",
                "resolver_version": "guideline-import-normalizer-v1",
                "confidence_score": float(chosen.get("score", 0.0)) if not is_ambiguous else 0.5,
                "candidate_list": candidate_list,
                "decision_reason": "ambiguous guideline import mention"
                if is_ambiguous
                else "matched from guideline import canonical name or alias",
                "status": "ambiguous" if is_ambiguous else "resolved",
                "kb_version": kb_version,
                "created_at": created_at,
            }
        for term_type, terms in (unresolved_terms or {}).items():
            for term in sorted({item for item in terms if item}):
                start = guide_text.find(term)
                if start < 0:
                    continue
                end = start + len(term)
                raw_mention = f"{kb_version}|unresolved|{term_type}|{term}|{start}|{end}"
                mention_id = f"mention_{hashlib.md5(raw_mention.encode('utf-8')).hexdigest()[:16]}"
                mentions[mention_id] = {
                    "mention_id": mention_id,
                    "source_type": "guideline_import",
                    "source_record_id": kb_version,
                    "surface_text": term,
                    "normalized_text": term.strip(),
                    "start_offset": start,
                    "end_offset": end,
                    "mention_type_guess": term_type,
                    "context_window": guide_text[
                        max(0, start - 30) : min(len(guide_text), end + 30)
                    ],
                    "kb_version": kb_version,
                    "created_at": created_at,
                }
                decision_id = f"normdec_{hashlib.md5((mention_id + 'unresolved').encode('utf-8')).hexdigest()[:16]}"
                decisions[decision_id] = {
                    "decision_id": decision_id,
                    "mention_id": mention_id,
                    "resolved_concept_id": None,
                    "canonical_name": None,
                    "resolver_type": "guideline_import_alias",
                    "resolver_version": "guideline-import-normalizer-v1",
                    "confidence_score": 0.0,
                    "candidate_list": [],
                    "decision_reason": f"unresolved {term_type} term from guideline import",
                    "status": "unresolved",
                    "kb_version": kb_version,
                    "created_at": created_at,
                }
        return mentions, decisions

    def _collect_unresolved_terms(self, drafts: dict[str, MaterialDraft]) -> dict[str, set[str]]:
        unresolved: dict[str, set[str]] = {}
        for draft in drafts.values():
            for term_type, terms in draft.unresolved_terms.items():
                unresolved.setdefault(term_type, set()).update(terms)
        return unresolved

    def _material_label(self, material_name: str) -> str:
        formula_suffixes = ("汤", "丸", "散", "饮", "方", "颗粒", "胶囊", "口服液")
        return "Formula" if material_name.endswith(formula_suffixes) else "Herb"

    def _dose_attributes(self, dose_value: str) -> dict[str, Any]:
        attrs: dict[str, Any] = {"dose_text": dose_value}
        range_match = re.search(
            r"(?P<min>\d+(?:\.\d+)?)\s*(?:-|~|～|至|到)\s*(?P<max>\d+(?:\.\d+)?)\s*(?P<unit>克|g|G|毫克|mg|ML|ml|毫升)?",
            dose_value,
        )
        single_match = re.search(
            r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>克|g|G|毫克|mg|ML|ml|毫升)",
            dose_value,
        )
        if range_match:
            attrs["dose_min"] = float(range_match.group("min"))
            attrs["dose_max"] = float(range_match.group("max"))
            attrs["dose_unit"] = self._normalize_dose_unit(range_match.group("unit"))
        elif single_match:
            value = float(single_match.group("value"))
            attrs["dose_min"] = value
            attrs["dose_max"] = value
            attrs["dose_unit"] = self._normalize_dose_unit(single_match.group("unit"))
        if any(token in dose_value for token in ("每日", "每天", "日一")):
            attrs["frequency"] = "daily"
        if "一剂" in dose_value:
            attrs["dose_count"] = 1
            attrs["dose_count_unit"] = "剂"
        return attrs

    def _acupoint_location_attributes(self, location_text: str | None) -> dict[str, Any]:
        if not location_text:
            return {}
        match = re.search(
            r"(?P<reference>[\u4e00-\u9fff]{1,12}?)(?P<direction>上|下|前|后|旁|内|外)(?P<distance>[一二三四五六七八九十\d.]+)(?P<unit>寸|分|厘米|cm)",
            location_text,
        )
        if not match:
            return {}
        return {
            "location_reference": match.group("reference"),
            "location_direction": match.group("direction"),
            "location_distance": self._parse_chinese_or_float_number(match.group("distance")),
            "location_unit": "cm" if match.group("unit") in {"厘米", "cm"} else match.group("unit"),
        }

    @staticmethod
    def _parse_chinese_or_float_number(value: str) -> float | None:
        chinese_digits = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        if value in chinese_digits:
            return float(chinese_digits[value])
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_dose_unit(unit: str | None) -> str | None:
        if not unit:
            return None
        normalized = unit.lower()
        if normalized == "克":
            return "g"
        if normalized == "毫克":
            return "mg"
        if normalized == "毫升":
            return "ml"
        return normalized

    def _validate_assertions(
        self,
        ontology_entities: dict[str, dict[str, Any]],
        ontology_assertions: dict[str, dict[str, Any]],
        relation_schemas: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        valid_assertions: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        schema_registry = RelationSchemaRegistry(relation_schemas or RELATION_CONSTRAINTS)
        for assertion in ontology_assertions.values():
            predicate = canonical_relation_code(str(assertion.get("predicate_type") or ""))
            assertion["predicate_type"] = predicate
            constraint = schema_registry.get(predicate)
            if constraint is None:
                warnings.append(
                    f"Assertion {assertion.get('assertion_id')} 的 relation={predicate} 未注册。"
                )
                continue

            subject_id = assertion.get("subject_entity_id")
            subject = ontology_entities.get(str(subject_id)) if subject_id else None
            if subject is None:
                warnings.append(f"Assertion {assertion.get('assertion_id')} 缺少合法 subject。")
                continue
            is_valid = True
            if subject.get("label") not in set(constraint["subject_labels"]):
                warnings.append(
                    f"Assertion {assertion.get('assertion_id')} 的 subject label={subject.get('label')} "
                    f"不满足 {predicate} 的 domain 约束。"
                )
                is_valid = False

            object_id = assertion.get("object_entity_id")
            if object_id:
                object_entity = ontology_entities.get(str(object_id))
                if object_entity is None:
                    warnings.append(f"Assertion {assertion.get('assertion_id')} 缺少合法 object。")
                    continue
                if object_entity.get("label") not in set(constraint["object_labels"]):
                    warnings.append(
                        f"Assertion {assertion.get('assertion_id')} 的 object label={object_entity.get('label')} "
                        f"不满足 {predicate} 的 range 约束。"
                    )
                    is_valid = False
            if is_valid:
                valid_assertions[str(assertion.get("assertion_id"))] = assertion
        return valid_assertions, warnings
