from __future__ import annotations

from uuid import UUID, uuid4

from ..exceptions import APIError
from ..schemas import RuleCreateRequest, RuleVersionCreateRequest, RuleVersionView, RuleView
from ..store import InMemoryStore
from ..utils import enum_value, paginate, utcnow


class RuleService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def list_rules(
        self,
        page: int,
        page_size: int,
        rule_type: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[RuleView], int, int, int]:
        items = []
        for rule in self.store.rules.values():
            if rule_type and rule["rule_type"] != rule_type:
                continue
            if status and rule["status"] != status:
                continue
            if keyword and keyword not in f'{rule["rule_code"]} {rule["rule_name"]} {rule.get("description", "")}':
                continue
            items.append(RuleView(**{k: rule[k] for k in RuleView.model_fields}))
        items.sort(key=lambda item: item.rule_code)
        total = len(items)
        page, page_size, total_pages = paginate(total, page, page_size)
        start = (page - 1) * page_size
        return items[start:start + page_size], total, page, total_pages

    def create_rule(self, payload: RuleCreateRequest) -> RuleView:
        if payload.rule_code in self.store.rule_code_index:
            raise APIError(status_code=409, code="conflict", message="rule_code already exists")
        now = utcnow()
        rule_id = uuid4()
        record = {
            "rule_id": rule_id,
            "rule_code": payload.rule_code,
            "rule_name": payload.rule_name,
            "rule_type": enum_value(payload.rule_type),
            "status": "active",
            "description": payload.description,
            "created_at": now,
            "updated_at": now,
        }
        with self.store.lock():
            self.store.rules[rule_id] = record
            self.store.rule_code_index[payload.rule_code] = rule_id
        self.store.persist_rule(record)
        return RuleView(**{k: record[k] for k in RuleView.model_fields})

    def get_rule(self, rule_id: UUID) -> dict:
        rule = self.store.rules.get(rule_id)
        if rule is None:
            raise APIError(status_code=404, code="not_found", message="Rule not found")
        versions = [
            RuleVersionView(
                rule_version_id=version["rule_version_id"],
                rule_id=version["rule_id"],
                version_no=version["version_no"],
                status=version["status"],
                priority=version["priority"],
                default_decision=version["default_decision"],
                risk_level=version["risk_level"],
                explanation_template=version["explanation_template"],
            )
            for version in self.store.rule_versions.values()
            if version["rule_id"] == rule_id
        ]
        versions.sort(key=lambda item: item.version_no, reverse=True)
        return {
            "rule": RuleView(**{k: rule[k] for k in RuleView.model_fields}),
            "versions": versions,
        }

    def create_rule_version(self, rule_id: UUID, payload: RuleVersionCreateRequest) -> RuleVersionView:
        if rule_id not in self.store.rules:
            raise APIError(status_code=404, code="not_found", message="Rule not found")
        now = utcnow()
        rule_version_id = uuid4()
        record = {
            "rule_version_id": rule_version_id,
            "rule_id": rule_id,
            "version_no": payload.version_no,
            "status": "draft",
            "priority": payload.priority,
            "default_decision": enum_value(payload.default_decision),
            "risk_level": enum_value(payload.risk_level),
            "conditions": payload.conditions,
            "action": payload.action,
            "explanation_template": payload.explanation_template,
            "published_by": None,
            "published_at": None,
            "rollback_from_version_id": None,
            "created_at": now,
            "updated_at": now,
        }
        with self.store.lock():
            self.store.rule_versions[rule_version_id] = record
        self.store.persist_rule_version(record)
        return RuleVersionView(
            rule_version_id=rule_version_id,
            rule_id=rule_id,
            version_no=payload.version_no,
            status="draft",
            priority=payload.priority,
            default_decision=enum_value(payload.default_decision),
            risk_level=enum_value(payload.risk_level),
            explanation_template=payload.explanation_template,
        )

    def publish_rule_version(self, rule_id: UUID, rule_version_id: UUID) -> RuleVersionView:
        if rule_id not in self.store.rules:
            raise APIError(status_code=404, code="not_found", message="Rule not found")
        version = self.store.rule_versions.get(rule_version_id)
        if version is None or version["rule_id"] != rule_id:
            raise APIError(status_code=404, code="not_found", message="Rule version not found")
        now = utcnow()
        with self.store.lock():
            version["status"] = "published"
            version["published_at"] = now
            version["updated_at"] = now
        self.store.persist_rule_version(version)
        return RuleVersionView(
            rule_version_id=version["rule_version_id"],
            rule_id=version["rule_id"],
            version_no=version["version_no"],
            status=version["status"],
            priority=version["priority"],
            default_decision=version["default_decision"],
            risk_level=version["risk_level"],
            explanation_template=version["explanation_template"],
        )
