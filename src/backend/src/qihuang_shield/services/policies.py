from __future__ import annotations

from uuid import UUID, uuid4

from ..exceptions import APIError
from ..schemas import PolicyCreateRequest, PolicyVersionCreateRequest, PolicyVersionView, PolicyView
from ..store import InMemoryStore
from ..utils import enum_value, paginate, utcnow


class PolicyService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def list_policies(
        self,
        page: int,
        page_size: int,
        tenant_id: UUID | None = None,
        status: str | None = None,
        policy_code: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[PolicyView], int, int, int]:
        items = []
        for policy in self.store.policies.values():
            if tenant_id and policy["tenant_id"] != tenant_id:
                continue
            if status and policy["status"] != status:
                continue
            if policy_code and policy["policy_code"] != policy_code:
                continue
            haystack = f'{policy["policy_code"]} {policy["policy_name"]} {policy.get("description", "")}'
            if keyword and keyword not in haystack:
                continue
            items.append(PolicyView(**{k: policy[k] for k in PolicyView.model_fields}))
        items.sort(key=lambda item: item.policy_code)
        total = len(items)
        page, page_size, total_pages = paginate(total, page, page_size)
        start = (page - 1) * page_size
        return items[start:start + page_size], total, page, total_pages

    def create_policy(self, payload: PolicyCreateRequest) -> PolicyView:
        if payload.tenant_id not in self.store.tenants:
            raise APIError(status_code=404, code="not_found", message="Tenant not found")
        composite_code = payload.policy_code
        if composite_code in self.store.policy_code_index:
            raise APIError(status_code=409, code="conflict", message="policy_code already exists")
        now = utcnow()
        policy_id = uuid4()
        record = {
            "policy_id": policy_id,
            "tenant_id": payload.tenant_id,
            "policy_code": payload.policy_code,
            "policy_name": payload.policy_name,
            "status": "active",
            "description": payload.description,
            "created_at": now,
            "updated_at": now,
        }
        with self.store.lock():
            self.store.policies[policy_id] = record
            self.store.policy_code_index[payload.policy_code] = policy_id
        self.store.persist_policy(record)
        return PolicyView(**{k: record[k] for k in PolicyView.model_fields})

    def get_policy(self, policy_id: UUID) -> dict:
        policy = self.store.policies.get(policy_id)
        if policy is None:
            raise APIError(status_code=404, code="not_found", message="Policy not found")
        versions = [
            PolicyVersionView(
                policy_version_id=version["policy_version_id"],
                policy_id=version["policy_id"],
                version_no=version["version_no"],
                status=version["status"],
                fallback_mode=version["fallback_mode"],
                low_confidence_decision=version["low_confidence_decision"],
            )
            for version in self.store.policy_versions.values()
            if version["policy_id"] == policy_id
        ]
        versions.sort(key=lambda item: item.version_no, reverse=True)
        return {
            "policy": PolicyView(**{k: policy[k] for k in PolicyView.model_fields}),
            "versions": versions,
        }

    def create_policy_version(self, policy_id: UUID, payload: PolicyVersionCreateRequest) -> PolicyVersionView:
        if policy_id not in self.store.policies:
            raise APIError(status_code=404, code="not_found", message="Policy not found")
        now = utcnow()
        policy_version_id = uuid4()
        record = {
            "policy_version_id": policy_version_id,
            "policy_id": policy_id,
            "version_no": payload.version_no,
            "status": "draft",
            "scenario_scope": [enum_value(item) for item in payload.scenario_scope],
            "content_type_scope": [enum_value(item) for item in payload.content_type_scope],
            "fallback_mode": payload.fallback_mode,
            "low_confidence_decision": enum_value(payload.low_confidence_decision),
            "config": payload.config,
            "rule_overrides": [item.model_dump() for item in payload.rule_overrides],
            "published_by": None,
            "published_at": None,
            "created_at": now,
            "updated_at": now,
        }
        with self.store.lock():
            self.store.policy_versions[policy_version_id] = record
        self.store.persist_policy_version(record)
        return PolicyVersionView(
            policy_version_id=policy_version_id,
            policy_id=policy_id,
            version_no=payload.version_no,
            status="draft",
            fallback_mode=payload.fallback_mode,
            low_confidence_decision=enum_value(payload.low_confidence_decision),
        )

    def publish_policy_version(self, policy_id: UUID, policy_version_id: UUID) -> PolicyVersionView:
        if policy_id not in self.store.policies:
            raise APIError(status_code=404, code="not_found", message="Policy not found")
        version = self.store.policy_versions.get(policy_version_id)
        if version is None or version["policy_id"] != policy_id:
            raise APIError(status_code=404, code="not_found", message="Policy version not found")
        now = utcnow()
        with self.store.lock():
            version["status"] = "published"
            version["published_at"] = now
            version["updated_at"] = now
        self.store.persist_policy_version(version)
        return PolicyVersionView(
            policy_version_id=version["policy_version_id"],
            policy_id=version["policy_id"],
            version_no=version["version_no"],
            status=version["status"],
            fallback_mode=version["fallback_mode"],
            low_confidence_decision=version["low_confidence_decision"],
        )
