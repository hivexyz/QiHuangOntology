from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable

from .guideline_import import GuidelineOntologyBundle, GuidelineOntologyExtractor


@dataclass(frozen=True, slots=True)
class GoldenConcept:
    concept_type: str
    standard_name: str


@dataclass(frozen=True, slots=True)
class GoldenAssertion:
    subject: str
    relation: str
    object: str


@dataclass(frozen=True, slots=True)
class GoldenCase:
    case_id: str
    guide_title: str
    guide_text: str
    expected_concepts: list[GoldenConcept] = field(default_factory=list)
    expected_assertions: list[GoldenAssertion] = field(default_factory=list)
    expected_evidence_texts: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SetMetric:
    expected: int
    predicted: int
    true_positive: int

    @property
    def precision(self) -> float:
        return self.true_positive / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.true_positive / self.expected if self.expected else 0.0

    @property
    def f1(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)

    def as_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected,
            "predicted": self.predicted,
            "true_positive": self.true_positive,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


class GoldenEvaluator:
    def __init__(self, extractor: GuidelineOntologyExtractor) -> None:
        self.extractor = extractor

    def evaluate(self, cases: Iterable[GoldenCase]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        buckets: dict[str, list[dict[str, Any]]] = {}
        for case in cases:
            bundle = self.extractor.extract(case.guide_title, case.guide_text, f"golden-{case.case_id}")
            item = self._evaluate_case(case, bundle)
            results.append(item)
            buckets.setdefault(item["extractor_engine"], []).append(item)
        return {
            "case_count": len(results),
            "overall": self._aggregate(results),
            "by_extractor_engine": {
                engine: self._aggregate(items)
                for engine, items in sorted(buckets.items())
            },
            "cases": results,
        }

    def _evaluate_case(self, case: GoldenCase, bundle: GuidelineOntologyBundle) -> dict[str, Any]:
        expected_concepts = {
            (item.concept_type, item.standard_name)
            for item in case.expected_concepts
        }
        predicted_concepts = {
            (str(item.get("label") or ""), str(item.get("standard_name") or ""))
            for item in bundle.ontology_entities.values()
        }
        expected_assertions = {
            (item.subject, item.relation, item.object)
            for item in case.expected_assertions
        }
        predicted_assertions = self._assertion_name_set(bundle)
        expected_evidence = {text.strip() for text in case.expected_evidence_texts if text.strip()}
        predicted_evidence = {
            str(item.get("source_text") or "").strip()
            for item in bundle.evidence_sources.values()
            if str(item.get("source_text") or "").strip()
        }
        concept_metric = self._set_metric(expected_concepts, predicted_concepts)
        assertion_metric = self._set_metric(expected_assertions, predicted_assertions)
        evidence_metric = self._set_metric(expected_evidence, predicted_evidence)
        return {
            "case_id": case.case_id,
            "extractor_engine": bundle.extractor_engine,
            "concepts": concept_metric.as_dict(),
            "assertions": assertion_metric.as_dict(),
            "evidence_texts": evidence_metric.as_dict(),
            "unresolved_count": sum(
                1 for item in bundle.normalization_decisions.values()
                if item.get("status") == "unresolved"
            ),
            "ambiguous_count": sum(
                1 for item in bundle.normalization_decisions.values()
                if item.get("status") == "ambiguous"
            ),
        }

    def _assertion_name_set(self, bundle: GuidelineOntologyBundle) -> set[tuple[str, str, str]]:
        result: set[tuple[str, str, str]] = set()
        for assertion in bundle.ontology_assertions.values():
            subject = bundle.ontology_entities.get(str(assertion.get("subject_entity_id") or "")) or {}
            obj = bundle.ontology_entities.get(str(assertion.get("object_entity_id") or "")) or {}
            result.add(
                (
                    str(subject.get("standard_name") or assertion.get("subject_entity_id") or ""),
                    str(assertion.get("predicate_type") or ""),
                    str(obj.get("standard_name") or assertion.get("object_value") or ""),
                )
            )
        return result

    @staticmethod
    def _set_metric(expected: set[Any], predicted: set[Any]) -> SetMetric:
        return SetMetric(
            expected=len(expected),
            predicted=len(predicted),
            true_positive=len(expected & predicted),
        )

    def _aggregate(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "case_count": len(items),
            "concepts": self._aggregate_metric(items, "concepts"),
            "assertions": self._aggregate_metric(items, "assertions"),
            "evidence_texts": self._aggregate_metric(items, "evidence_texts"),
            "unresolved_count": sum(int(item["unresolved_count"]) for item in items),
            "ambiguous_count": sum(int(item["ambiguous_count"]) for item in items),
        }

    @staticmethod
    def _aggregate_metric(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
        metric = SetMetric(
            expected=sum(int(item[key]["expected"]) for item in items),
            predicted=sum(int(item[key]["predicted"]) for item in items),
            true_positive=sum(int(item[key]["true_positive"]) for item in items),
        )
        return metric.as_dict()


def load_golden_cases(path: str | Path) -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        raw = json.loads(stripped)
        expected = raw.get("expected") or {}
        cases.append(
            GoldenCase(
                case_id=str(raw.get("case_id") or f"case-{line_number}"),
                guide_title=str(raw.get("guide_title") or raw.get("case_id") or f"case-{line_number}"),
                guide_text=str(raw.get("guide_text") or ""),
                expected_concepts=[
                    GoldenConcept(
                        concept_type=str(item.get("type") or item.get("concept_type") or ""),
                        standard_name=str(item.get("name") or item.get("standard_name") or ""),
                    )
                    for item in expected.get("concepts", [])
                ],
                expected_assertions=[
                    GoldenAssertion(
                        subject=str(item.get("subject") or ""),
                        relation=str(item.get("relation") or ""),
                        object=str(item.get("object") or ""),
                    )
                    for item in expected.get("assertions", [])
                ],
                expected_evidence_texts=[str(item) for item in expected.get("evidence_texts", [])],
            )
        )
    return cases
