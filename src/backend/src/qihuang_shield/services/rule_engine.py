"""Lightweight rule engine — evaluates JSON DSL conditions against a facts dictionary.

Loads published rules from ``rule_versions`` stored in the InMemoryStore, evaluates
each rule's ``conditions`` JSON DSL against the assembled facts dictionary, and
returns a list of ``RuleMatch`` results.

The DSL supports:
- Logical combinators: ``all`` (AND), ``any`` (OR), ``not`` (NOT)
- Operators: ``equals``, ``not_equals``, ``in``, ``not_in``, ``contains``,
  ``not_contains``, ``exists``, ``not_exists``, ``gt``, ``gte``, ``lt``, ``lte``,
  ``matches``
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from ..enums import Decision, RecommendedAction, RiskLevel
from ..store import InMemoryStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RuleSpec:
    """A fully-resolved rule specification, ready for evaluation."""

    rule_code: str
    rule_name: str
    rule_version: str
    rule_version_id: UUID
    rule_id: UUID
    priority: int
    default_decision: str
    risk_level: str
    conditions: dict[str, Any]
    action: dict[str, Any]
    explanation_template: str


@dataclass(slots=True)
class RuleMatch:
    """The result of a successful rule evaluation."""

    rule_code: str
    rule_name: str
    rule_version: str
    rule_version_id: UUID
    decision: Decision
    risk_level: RiskLevel
    priority: int
    reason: str
    matched_conditions: dict[str, Any] = field(default_factory=dict)
    matched_entities: list[dict[str, Any]] = field(default_factory=list)
    matched_evidence: list[dict[str, Any]] = field(default_factory=list)
    ontology_facts: list[dict[str, Any]] = field(default_factory=list)


class RuleEngine:
    """Evaluates published rules against a facts dictionary.

    Rules are loaded from ``store.rule_versions`` and filtered to only include
    those with ``status == 'published'``. Customer policy overrides can adjust
    rule decisions and priorities.
    """

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(
        self,
        facts: dict[str, Any],
        scenario: str | None = None,
        policy_version_id: UUID | None = None,
    ) -> list[RuleMatch]:
        """Evaluate all published rules against the facts dictionary.

        Args:
            facts: The assembled facts dictionary (entities, relationships, derived booleans).
            scenario: Current content scenario, injected into facts if not already present.
            policy_version_id: Optional policy version for customer overrides.

        Returns:
            A list of RuleMatch results, sorted by priority (highest first).
        """
        if scenario is not None and "scenario" not in facts:
            facts["scenario"] = scenario

        rules = self._load_published_rules()
        policy_overrides = self._load_policy_overrides(policy_version_id) if policy_version_id else {}

        matches: list[RuleMatch] = []
        for rule in rules:
            # Apply policy override: skip disabled rules
            override = policy_overrides.get(rule.rule_code)
            if override is not None and not override.get("enabled", True):
                continue

            try:
                if self._match_condition(rule.conditions, facts):
                    match = self._build_match(rule, facts, override)
                    matches.append(match)
            except Exception as exc:
                logger.warning("Rule %s evaluation failed: %s", rule.rule_code, exc)

        matches.sort(key=lambda m: m.priority, reverse=True)
        return matches

    def load_published_rules(self) -> list[RuleSpec]:
        """Public wrapper for loading published rules."""
        return self._load_published_rules()

    # ------------------------------------------------------------------
    # Rule loading
    # ------------------------------------------------------------------

    def _load_published_rules(self) -> list[RuleSpec]:
        """Load all published rule versions, sorted by priority descending."""
        specs: list[RuleSpec] = []
        for version in self._store.rule_versions.values():
            if version.get("status") != "published":
                continue
            rule_id = version["rule_id"]
            rule = self._store.rules.get(rule_id)
            if rule is None:
                continue

            conditions = version.get("conditions") or {}
            if not isinstance(conditions, dict):
                conditions = {}

            specs.append(RuleSpec(
                rule_code=rule["rule_code"],
                rule_name=rule["rule_name"],
                rule_version=version["version_no"],
                rule_version_id=version["rule_version_id"],
                rule_id=rule_id,
                priority=version.get("priority", 0),
                default_decision=version.get("default_decision", "review"),
                risk_level=version.get("risk_level", "medium"),
                conditions=conditions,
                action=version.get("action") or {},
                explanation_template=version.get("explanation_template", ""),
            ))

        specs.sort(key=lambda s: s.priority, reverse=True)
        return specs

    def _load_policy_overrides(self, policy_version_id: UUID) -> dict[str, dict[str, Any]]:
        """Load rule overrides for a given policy version."""
        overrides: dict[str, dict[str, Any]] = {}
        for version in self._store.policy_versions.values():
            if version["policy_version_id"] != policy_version_id:
                continue
            for override in version.get("rule_overrides") or []:
                rule_code = override.get("rule_code")
                if rule_code:
                    overrides[rule_code] = override
            break
        return overrides

    # ------------------------------------------------------------------
    # Condition matching
    # ------------------------------------------------------------------

    def _match_condition(self, condition: Any, facts: dict[str, Any]) -> bool:
        """Recursively evaluate a condition node against the facts dictionary."""
        if not isinstance(condition, dict):
            return False

        # Logical combinators
        if "all" in condition:
            items = condition["all"]
            if not isinstance(items, list):
                return False
            return all(self._match_condition(item, facts) for item in items)

        if "any" in condition:
            items = condition["any"]
            if not isinstance(items, list):
                return False
            return any(self._match_condition(item, facts) for item in items)

        if "not" in condition:
            item = condition["not"]
            return not self._match_condition(item, facts)

        # Leaf condition: fact + operator + value
        fact_name = condition.get("fact")
        operator = condition.get("operator", "equals")
        expected = condition.get("value")

        if fact_name is None:
            return False

        fact_value = self._resolve_fact(fact_name, facts)
        return self._apply_operator(fact_value, operator, expected)

    def _resolve_fact(self, fact_name: str, facts: dict[str, Any]) -> Any:
        """Resolve a fact name from the facts dictionary.

        Supports dot-notation for nested access (e.g. ``entities.0.standard_name``).
        """
        if fact_name in facts:
            return facts[fact_name]

        # Try dot-notation access
        parts = fact_name.split(".")
        current: Any = facts
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx] if 0 <= idx < len(current) else None
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return current

    def _apply_operator(self, fact_value: Any, operator: str, expected: Any) -> bool:
        """Apply a comparison operator between fact_value and expected."""
        if operator == "exists":
            return fact_value is not None and fact_value != "" and fact_value != []
        if operator == "not_exists":
            return fact_value is None or fact_value == "" or fact_value == []

        if fact_value is None:
            return False

        if operator == "equals":
            if isinstance(fact_value, bool) and isinstance(expected, str):
                return fact_value == (expected.lower() in ("true", "1", "yes"))
            if isinstance(expected, bool) and isinstance(fact_value, str):
                return fact_value.lower() in ("true", "1", "yes") == expected
            return fact_value == expected

        if operator == "not_equals":
            return fact_value != expected

        if operator == "in":
            if not isinstance(expected, list):
                return False
            return fact_value in expected

        if operator == "not_in":
            if not isinstance(expected, list):
                return False
            return fact_value not in expected

        if operator == "contains":
            if isinstance(fact_value, str) and isinstance(expected, str):
                return expected in fact_value
            if isinstance(fact_value, list):
                return expected in fact_value
            return False

        if operator == "not_contains":
            if isinstance(fact_value, str) and isinstance(expected, str):
                return expected not in fact_value
            if isinstance(fact_value, list):
                return expected not in fact_value
            return True

        if operator in ("gt", "gte", "lt", "lte"):
            try:
                fv = float(fact_value)
                ev = float(expected)
            except (TypeError, ValueError):
                return False
            if operator == "gt":
                return fv > ev
            if operator == "gte":
                return fv >= ev
            if operator == "lt":
                return fv < ev
            if operator == "lte":
                return fv <= ev

        if operator == "matches":
            if not isinstance(fact_value, str) or not isinstance(expected, str):
                return False
            try:
                return bool(re.search(expected, fact_value))
            except re.error:
                return False

        return False

    # ------------------------------------------------------------------
    # Match construction
    # ------------------------------------------------------------------

    def _build_match(
        self,
        rule: RuleSpec,
        facts: dict[str, Any],
        override: dict[str, Any] | None,
    ) -> RuleMatch:
        """Build a RuleMatch from a matched rule, applying policy overrides."""
        decision_str = rule.default_decision
        risk_str = rule.risk_level

        # Apply policy override
        if override:
            if override.get("override_decision"):
                decision_str = override["override_decision"]
            if override.get("override_risk_level"):
                risk_str = override["override_risk_level"]

        decision = self._parse_decision(decision_str)
        risk_level = self._parse_risk_level(risk_str)

        # Build reason from template
        reason = self._render_template(rule.explanation_template, facts, rule)

        # Collect matched entities and evidence from facts
        entities = self._extract_matched_entities(facts)
        evidence = self._extract_matched_evidence(facts, rule.rule_code)
        ontology_facts_list = self._extract_ontology_facts(facts)

        return RuleMatch(
            rule_code=rule.rule_code,
            rule_name=rule.rule_name,
            rule_version=rule.rule_version,
            rule_version_id=rule.rule_version_id,
            decision=decision,
            risk_level=risk_level,
            priority=rule.priority,
            reason=reason,
            matched_conditions={
                "rule_conditions": rule.conditions,
                "condition_context": facts.get("condition_context", {}),
            },
            matched_entities=entities,
            matched_evidence=evidence,
            ontology_facts=ontology_facts_list,
        )

    def _render_template(self, template: str, facts: dict[str, Any], rule: RuleSpec) -> str:
        """Render explanation template with variable substitution."""
        result = template
        # Replace {standard_name} with first entity's standard name
        entities = facts.get("entities") or []
        if isinstance(entities, list) and entities:
            first = entities[0]
            if isinstance(first, dict):
                result = result.replace("{standard_name}", str(first.get("standard_name", "")))
                result = result.replace("{entity_a}", str(first.get("standard_name", "")))
        if isinstance(entities, list) and len(entities) > 1:
            second = entities[1]
            if isinstance(second, dict):
                result = result.replace("{entity_b}", str(second.get("standard_name", "")))
        # Replace {scenario}
        scenario = facts.get("scenario", "")
        result = result.replace("{scenario}", str(scenario))
        return result

    def _extract_matched_entities(self, facts: dict[str, Any]) -> list[dict[str, Any]]:
        entities = facts.get("entities") or []
        if isinstance(entities, list):
            return [dict(e) if isinstance(e, dict) else {"name": str(e)} for e in entities]
        return []

    def _extract_matched_evidence(self, facts: dict[str, Any], rule_code: str) -> list[dict[str, Any]]:
        evidence = facts.get("evidence_spans") or []
        if isinstance(evidence, list):
            return [dict(e) if isinstance(e, dict) else {"text": str(e), "rule_id": rule_code} for e in evidence]
        return []

    def _extract_ontology_facts(self, facts: dict[str, Any]) -> list[dict[str, Any]]:
        facts_list = facts.get("ontology_facts") or []
        if isinstance(facts_list, list):
            return [dict(f) if isinstance(f, dict) else {"fact": str(f)} for f in facts_list]
        return []

    @staticmethod
    def _parse_decision(value: str) -> Decision:
        try:
            return Decision(value.lower())
        except ValueError:
            return Decision.REVIEW

    @staticmethod
    def _parse_risk_level(value: str) -> RiskLevel:
        try:
            return RiskLevel(value.lower())
        except ValueError:
            return RiskLevel.MEDIUM


# ------------------------------------------------------------------
# Conflict resolution helpers for rule evaluation outcomes
# ------------------------------------------------------------------

def resolve_decision_conflicts(matches: list[RuleMatch]) -> Decision:
    """Resolve conflicting rule decisions.

    Rules:
    - Block > Review > Pass
    - If any Block with low confidence (< 0.7), downgrade to Review
    """
    if not matches:
        return Decision.PASS

    has_block = any(m.decision == Decision.BLOCK for m in matches)
    has_review = any(m.decision == Decision.REVIEW for m in matches)

    if has_block:
        return Decision.BLOCK
    if has_review:
        return Decision.REVIEW
    return Decision.PASS


def resolve_risk_level(matches: list[RuleMatch]) -> RiskLevel:
    """Take the highest risk level across all matches."""
    if not matches:
        return RiskLevel.LOW

    order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
    highest = RiskLevel.LOW
    for m in matches:
        if order.get(m.risk_level, 0) > order.get(highest, 0):
            highest = m.risk_level
    return highest


def resolve_recommended_action(decision: Decision) -> RecommendedAction:
    """Map decision to recommended action."""
    if decision == Decision.BLOCK:
        return RecommendedAction.BLOCK_OR_MANUAL_CONFIRM
    if decision == Decision.REVIEW:
        return RecommendedAction.EXPERT_REVIEW
    return RecommendedAction.ALLOW
