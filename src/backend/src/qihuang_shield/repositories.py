from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from .platform_services import CacheControlService
from .store import InMemoryStore


_STORE_STATE_FIELDS = (
    "tenants",
    "tenant_code_index",
    "api_clients",
    "users",
    "user_email_index",
    "memberships",
    "rules",
    "rule_code_index",
    "rule_versions",
    "policies",
    "policy_code_index",
    "policy_versions",
    "kb_versions",
    "import_jobs",
    "ontology_entities",
    "knowledge_cards",
    "ontology_assertions",
    "evidence_sources",
    "concept_aliases",
    "guideline_documents",
    "mentions",
    "normalization_decisions",
    "knowledge_card_projections",
    "relation_schemas",
    "mention_normalization_logs",
    "audit_logs",
    "tokens",
)


class UnitOfWork(ABC):
    @abstractmethod
    def begin(self) -> "UnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def defer(self, action: Callable[[], None]) -> None:
        raise NotImplementedError

    def __enter__(self) -> "UnitOfWork":
        return self.begin()

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()


class StoreBackedUnitOfWork(UnitOfWork):
    """MVP transaction boundary for in-memory backed repository operations.

    For the current codebase this provides deterministic begin/commit/rollback
    semantics over the in-memory snapshot used by tests and local development.
    """

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._lock = None
        self._snapshot: dict[str, Any] | None = None
        self._after_commit_actions: list[Callable[[], None]] = []
        self._active = False

    def begin(self) -> "StoreBackedUnitOfWork":
        if self._active:
            return self
        self._lock = self._store.lock()
        self._lock.acquire()
        self._snapshot = {
            field_name: self._store.snapshot(getattr(self._store, field_name))
            for field_name in _STORE_STATE_FIELDS
        }
        setattr(self._store, "_active_unit_of_work", self)
        self._active = True
        return self

    def commit(self) -> None:
        if not self._active:
            return
        try:
            for action in self._after_commit_actions:
                action()
        except Exception:
            self.rollback()
            raise
        self._snapshot = None
        self._after_commit_actions = []
        self._active = False
        if getattr(self._store, "_active_unit_of_work", None) is self:
            setattr(self._store, "_active_unit_of_work", None)
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def rollback(self) -> None:
        if not self._active:
            return
        if self._snapshot is not None:
            for field_name, value in self._snapshot.items():
                setattr(self._store, field_name, value)
        self._snapshot = None
        self._after_commit_actions = []
        self._active = False
        if getattr(self._store, "_active_unit_of_work", None) is self:
            setattr(self._store, "_active_unit_of_work", None)
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    def defer(self, action: Callable[[], None]) -> None:
        if not self._active:
            action()
            return
        self._after_commit_actions.append(action)


def _persist_or_defer(store: InMemoryStore, action: Callable[[], None]) -> None:
    active_uow = getattr(store, "_active_unit_of_work", None)
    if isinstance(active_uow, StoreBackedUnitOfWork) and active_uow._active:
        active_uow.defer(action)
        return
    action()


class UserRepository(ABC):
    @abstractmethod
    def get(self, user_id: UUID) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_by_email(self, email: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, user: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class ApiClientRepository(ABC):
    @abstractmethod
    def get_by_key(self, client_key: str) -> dict[str, Any] | None:
        raise NotImplementedError


class TenantUserRoleRepository(ABC):
    @abstractmethod
    def list_active_by_user(self, user_id: UUID) -> list[dict[str, Any]]:
        raise NotImplementedError


class AuthTokenRepository(ABC):
    @abstractmethod
    def get_user_id(self, token: str) -> UUID | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, token: str, user_id: UUID) -> None:
        raise NotImplementedError


class AuditLogRepository(ABC):
    @abstractmethod
    def save(self, audit_log: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class CacheProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def invalidate(self, key: str) -> None:
        raise NotImplementedError


class SnapshotProvider(ABC):
    @abstractmethod
    def get_active_kb_snapshot(self) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def refresh(self, version_id: UUID) -> dict[str, Any] | None:
        raise NotImplementedError


class StoreBackedUserRepository(UserRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get(self, user_id: UUID) -> dict[str, Any] | None:
        user = self._store.users.get(user_id)
        return self._store.snapshot(user) if user is not None else None

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        user_id = self._store.user_email_index.get(email)
        return self.get(user_id) if user_id is not None else None

    def save(self, user: dict[str, Any]) -> dict[str, Any]:
        record = self._store.snapshot(user)
        user_id = record["user_id"]
        previous = self._store.users.get(user_id)
        with self._store.lock():
            if previous is not None:
                previous_email = previous.get("email")
                if previous_email and previous_email != record.get("email"):
                    self._store.user_email_index.pop(previous_email, None)
            self._store.users[user_id] = record
            if record.get("email"):
                self._store.user_email_index[record["email"]] = user_id
        _persist_or_defer(self._store, lambda: self._store.persist_user(record))
        return self._store.snapshot(record)


class StoreBackedApiClientRepository(ApiClientRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get_by_key(self, client_key: str) -> dict[str, Any] | None:
        for client in self._store.api_clients.values():
            if client.get("client_key") != client_key:
                continue
            record = self._store.snapshot(client)
            tenant = self._store.tenants.get(record["tenant_id"])
            record["tenant_code"] = tenant.get("tenant_code") if tenant is not None else None
            return record
        return None


class StoreBackedTenantUserRoleRepository(TenantUserRoleRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def list_active_by_user(self, user_id: UUID) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for membership in self._store.memberships.values():
            if membership.get("user_id") != user_id or membership.get("status") != "active":
                continue
            tenant = self._store.tenants.get(membership["tenant_id"])
            if tenant is None or tenant.get("status") != "active":
                continue
            records.append(
                {
                    "membership_id": membership["membership_id"],
                    "tenant_id": membership["tenant_id"],
                    "tenant_code": tenant["tenant_code"],
                    "role_code": membership["role_code"],
                    "status": membership["status"],
                }
            )
        records.sort(key=lambda item: (item["tenant_code"], item["role_code"]))
        return self._store.snapshot(records)


class StoreBackedAuthTokenRepository(AuthTokenRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def get_user_id(self, token: str) -> UUID | None:
        return self._store.tokens.get(token)

    def save(self, token: str, user_id: UUID) -> None:
        with self._store.lock():
            self._store.tokens[token] = user_id
        _persist_or_defer(self._store, lambda: self._store.persist_token(token, user_id))


class StoreBackedAuditLogRepository(AuditLogRepository):
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def save(self, audit_log: dict[str, Any]) -> dict[str, Any]:
        record = self._store.snapshot(audit_log)
        audit_id = record["audit_id"]
        with self._store.lock():
            self._store.audit_logs[audit_id] = record
        _persist_or_defer(self._store, lambda: self._store.persist_audit_log(record))
        return self._store.snapshot(record)


class M12CacheProvider(CacheProvider):
    def __init__(self, cache_control_service: CacheControlService) -> None:
        self._cache = cache_control_service

    def get(self, key: str) -> Any:
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._cache.set(key, value, ttl_seconds=ttl_seconds)

    def invalidate(self, key: str) -> None:
        self._cache.invalidate(key)


@dataclass(slots=True)
class StoreBackedSnapshotProvider(SnapshotProvider):
    store: InMemoryStore
    cache_provider: CacheProvider

    def get_active_kb_snapshot(self) -> dict[str, Any] | None:
        published_versions = [version for version in self.store.kb_versions.values() if version.get("status") == "published"]
        if not published_versions:
            return None
        active_version = sorted(
            published_versions,
            key=lambda item: item.get("published_at") or item.get("created_at"),
            reverse=True,
        )[0]
        cache_key = self._cache_key(active_version["kb_version_id"])
        cached = self.cache_provider.get(cache_key)
        if cached is not None:
            return self.store.snapshot(cached)
        snapshot = {
            "kb_version_id": active_version["kb_version_id"],
            "version_code": active_version.get("version_code"),
            "ontology_entities": self.store.snapshot(self.store.ontology_entities),
            "knowledge_card_projections": self.store.snapshot(self.store.knowledge_card_projections),
            # Keep a compatibility mirror while downstream consumers migrate.
            "knowledge_cards": self.store.snapshot(self.store.knowledge_card_projections),
        }
        self.cache_provider.set(cache_key, snapshot)
        self.cache_provider.set("kb_snapshot:active", {"version_id": active_version["kb_version_id"]})
        return self.store.snapshot(snapshot)

    def refresh(self, version_id: UUID) -> dict[str, Any] | None:
        self.cache_provider.invalidate(self._cache_key(version_id))
        self.cache_provider.invalidate("kb_snapshot:active")
        return self.get_active_kb_snapshot()

    @staticmethod
    def _cache_key(version_id: UUID) -> str:
        return f"kb_snapshot:{version_id}"
