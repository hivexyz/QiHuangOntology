from __future__ import annotations

import base64
import binascii
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Callable, Literal
from uuid import UUID, uuid4

from fastapi.exceptions import RequestValidationError

from .exceptions import APIError
from .schemas import ErrorDetail, ErrorEnvelope, ErrorInfo, MetaInfo, RequestContext, SuccessEnvelope
from .utils import new_trace_id, utcnow


logger = logging.getLogger(__name__)

_TRACE_ID_CTX: ContextVar[str | None] = ContextVar("qhs_trace_id", default=None)
_REQUEST_CONTEXT_CTX: ContextVar[RequestContext | None] = ContextVar(
    "qhs_request_context",
    default=None,
)

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "api_secret",
    "authorization",
    "client_secret",
    "client_secret_hash",
    "password",
    "password_hash",
    "secret",
    "signature",
    "token",
}

_DEV_SECURITY_SECRET_KEY = "qihuang-shield-dev-secret-key"


def hash_password(value: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        value.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return "scrypt$16384$8$1${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


class TraceService:
    def bind_trace_id(self, trace_id: str) -> Token[str | None]:
        return _TRACE_ID_CTX.set(trace_id)

    def reset_trace_id(self, token: Token[str | None]) -> None:
        _TRACE_ID_CTX.reset(token)

    def current_trace_id(self) -> str | None:
        return _TRACE_ID_CTX.get()

    def bind_request_context(self, context: RequestContext) -> Token[RequestContext | None]:
        return _REQUEST_CONTEXT_CTX.set(context)

    def reset_request_context(self, token: Token[RequestContext | None]) -> None:
        _REQUEST_CONTEXT_CTX.reset(token)

    def current_request_context(self) -> RequestContext | None:
        return _REQUEST_CONTEXT_CTX.get()

    def ensure_trace_id(self) -> str:
        trace_id = self.current_trace_id()
        if trace_id:
            return trace_id
        trace_id = new_trace_id()
        _TRACE_ID_CTX.set(trace_id)
        return trace_id


class ResponseEnvelopeFactory:
    def __init__(self, trace_service: TraceService) -> None:
        self._trace_service = trace_service

    def success(
        self,
        *,
        data: Any = None,
        trace_id: str | None = None,
        meta: MetaInfo | None = None,
    ) -> SuccessEnvelope:
        resolved_trace_id = trace_id or self._trace_service.current_trace_id() or ""
        return SuccessEnvelope(trace_id=resolved_trace_id, data=data, meta=meta)

    def error(
        self,
        *,
        code: str,
        message: str,
        trace_id: str | None = None,
        retryable: bool = False,
        details: list[ErrorDetail] | None = None,
    ) -> ErrorEnvelope:
        resolved_trace_id = trace_id or self._trace_service.current_trace_id() or ""
        return ErrorEnvelope(
            trace_id=resolved_trace_id,
            error=ErrorInfo(
                code=code,
                message=message,
                retryable=retryable,
                details=details or [],
            ),
        )


class ExceptionMapper:
    def to_error_envelope(
        self,
        exc: Exception,
        *,
        trace_id: str,
    ) -> tuple[int, ErrorEnvelope]:
        if isinstance(exc, APIError):
            details = [
                ErrorDetail(field=item.get("field"), message=str(item.get("message", "")))
                for item in exc.details
            ]
            return exc.status_code, ErrorEnvelope(
                trace_id=trace_id,
                error=ErrorInfo(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                    details=details,
                ),
            )

        if isinstance(exc, RequestValidationError):
            details = [
                ErrorDetail(
                    field=".".join(str(part) for part in item["loc"]),
                    message=item["msg"],
                )
                for item in exc.errors()
            ]
            return 400, ErrorEnvelope(
                trace_id=trace_id,
                error=ErrorInfo(
                    code="invalid_request",
                    message="Request validation failed",
                    retryable=False,
                    details=details,
                ),
            )

        return 500, ErrorEnvelope(
            trace_id=trace_id,
            error=ErrorInfo(
                code="internal_error",
                message="Internal server error",
                retryable=False,
                details=[],
            ),
        )


class ConfigService:
    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._values: dict[str, Any] = {
            "cache.default_ttl_seconds": int(
                os.getenv("QHS_CACHE_DEFAULT_TTL_SECONDS", "300").strip() or "300",
            ),
            "circuit_breaker.failure_threshold": int(
                os.getenv("QHS_CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5").strip() or "5",
            ),
            "circuit_breaker.reset_timeout_seconds": int(
                os.getenv("QHS_CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS", "60").strip() or "60",
            ),
            "feature_flags": os.getenv("QHS_FEATURE_FLAGS", ""),
            "security.secret_key": os.getenv("QHS_SECURITY_SECRET_KEY", "").strip(),
            "security.allow_insecure_dev_secret": bool(
                getattr(settings, "allow_insecure_dev_secret", False),
            ),
        }

    def health_snapshot(self) -> dict[str, Any]:
        settings = self._settings
        postgres_dsn = getattr(settings, "postgres_dsn", "")
        safe_postgres_dsn = postgres_dsn
        if "@" in postgres_dsn and ":" in postgres_dsn.split("@", 1)[0]:
            left, right = postgres_dsn.split("@", 1)
            proto, creds = left.split("://", 1) if "://" in left else ("postgresql", left)
            if ":" in creds:
                user = creds.split(":", 1)[0]
                safe_postgres_dsn = f"{proto}://{user}:***@{right}"
        return {
            "storage_backend": getattr(settings, "storage_backend", None),
            "db_auto_init": getattr(settings, "db_auto_init", None),
            "postgres": {
                "dsn_configured": bool(postgres_dsn),
                "dsn_masked": safe_postgres_dsn,
                "host": getattr(settings, "postgres_host", None),
                "port": getattr(settings, "postgres_port", None),
                "database": getattr(settings, "postgres_db", None),
                "pool_size": getattr(settings, "postgres_pool_size", None),
                "max_overflow": getattr(settings, "postgres_max_overflow", None),
            },
            "neo4j": {
                "uri": getattr(settings, "neo4j_uri", None),
                "database": getattr(settings, "neo4j_database", None),
                "configured": bool(getattr(settings, "neo4j_uri", None)),
            },
            "openai_chat": {
                "ready": getattr(settings, "openai_chat_ready", False),
                "base_url": getattr(settings, "openai_base_url", None),
                "model": getattr(settings, "openai_model", None),
                "api_key_configured": bool(getattr(settings, "openai_api_key", "")),
            },
            "embedding": {
                "ready": getattr(settings, "embedding_ready", False),
                "base_url": getattr(settings, "openai_embedding_base_url", None),
                "model": getattr(settings, "openai_embedding_model", None),
                "dimension": getattr(settings, "openai_embedding_dimension", None),
            },
            "milvus": {
                "ready": getattr(settings, "milvus_ready", False),
                "host": getattr(settings, "milvus_host", None),
                "port": getattr(settings, "milvus_port", None),
                "collection": getattr(settings, "milvus_collection_name", None),
                "dimension": getattr(settings, "milvus_dimension", None),
                "index_type": getattr(settings, "milvus_index_type", None),
                "metric_type": getattr(settings, "milvus_metric_type", None),
            },
            "qhs_llm": {
                "ready": getattr(settings, "llm_ready", False),
                "enabled": getattr(settings, "llm_enabled", False),
                "base_url": getattr(settings, "llm_base_url", None),
                "endpoint": getattr(settings, "llm_endpoint", None),
                "model": getattr(settings, "llm_model", None),
            },
        }

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._values:
            return self._values[key]
        attr_name = key.replace(".", "_")
        if hasattr(self._settings, attr_name):
            return getattr(self._settings, attr_name)
        return default

    def set_override(self, key: str, value: Any) -> None:
        self._values[key] = value


class SecurityService:
    def __init__(self, config_service: ConfigService) -> None:
        self._config = config_service

    def hash_password(self, value: str) -> str:
        return hash_password(value)

    def verify_password(self, plain_text: str, hashed_value: str | None) -> bool:
        if not isinstance(plain_text, str) or not isinstance(hashed_value, str):
            return False
        if not hashed_value.startswith("scrypt$"):
            return False
        try:
            _, n_value, r_value, p_value, salt_value, digest_value = hashed_value.split("$", 5)
            salt = base64.b64decode(salt_value.encode("ascii"), altchars=b"-_", validate=True)
            expected = base64.b64decode(digest_value.encode("ascii"), altchars=b"-_", validate=True)
            if not salt or not expected:
                return False
            actual = hashlib.scrypt(
                plain_text.encode("utf-8"),
                salt=salt,
                n=int(n_value),
                r=int(r_value),
                p=int(p_value),
                dklen=len(expected),
            )
            return hmac.compare_digest(actual, expected)
        except (binascii.Error, UnicodeError, ValueError, TypeError, OverflowError):
            return False

    def sign(self, payload: dict[str, Any] | str) -> str:
        if isinstance(payload, str):
            serialized = payload
        else:
            serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        payload_bytes = serialized.encode("utf-8")
        signature = hmac.new(
            self._secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).digest()
        encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii")
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii")
        return f"{encoded_payload}.{encoded_signature}"

    def verify(self, token: str) -> dict[str, Any] | str:
        if not isinstance(token, str) or not token:
            raise APIError(status_code=401, code="unauthorized", message="Invalid signature token")
        payload_part, separator, signature_part = token.partition(".")
        if not separator or not payload_part or not signature_part:
            raise APIError(status_code=401, code="unauthorized", message="Invalid signature token")
        try:
            payload_bytes = base64.b64decode(payload_part.encode("ascii"), altchars=b"-_", validate=True)
            signature = base64.b64decode(signature_part.encode("ascii"), altchars=b"-_", validate=True)
        except (binascii.Error, UnicodeError, ValueError, TypeError) as exc:
            raise APIError(status_code=401, code="unauthorized", message="Invalid signature token") from exc

        expected_signature = hmac.new(
            self._secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(signature, expected_signature):
            raise APIError(status_code=401, code="unauthorized", message="Invalid signature token")

        try:
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError(status_code=401, code="unauthorized", message="Invalid signature token") from exc
        if not isinstance(payload, dict):
            raise APIError(status_code=401, code="unauthorized", message="Invalid signature token")

        expires_at = payload.get("exp")
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
            raise APIError(status_code=401, code="unauthorized", message="Invalid signature token")
        if expires_at <= utcnow().timestamp():
            raise APIError(status_code=401, code="unauthorized", message="Expired signature token")
        return payload

    @property
    def _secret_key(self) -> str:
        configured_key = str(self._config.get("security.secret_key", "") or "").strip()
        if configured_key:
            return configured_key
        if self._config.get("security.allow_insecure_dev_secret", False):
            return _DEV_SECURITY_SECRET_KEY
        raise RuntimeError("QHS_SECURITY_SECRET_KEY must be configured outside demo mode")


@dataclass(slots=True)
class CacheEntry:
    value: Any
    expires_at: datetime | None = None


class CacheControlService:
    def __init__(self, config_service: ConfigService) -> None:
        self._config = config_service
        self._entries: dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at and entry.expires_at <= utcnow():
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else int(self._config.get("cache.default_ttl_seconds", 300))
        expires_at = utcnow() + timedelta(seconds=ttl) if ttl > 0 else None
        self._entries[key] = CacheEntry(value=value, expires_at=expires_at)

    def invalidate(self, key: str) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()


class FeatureFlagService:
    def __init__(self, config_service: ConfigService) -> None:
        self._config = config_service

    def is_enabled(self, flag_key: str, context: dict[str, Any] | None = None) -> bool:
        context = context or {}
        raw_flags = str(self._config.get("feature_flags", "") or "")
        flags: dict[str, bool] = {}
        for item in raw_flags.split(","):
            stripped = item.strip()
            if not stripped:
                continue
            key, _, value = stripped.partition("=")
            flags[key.strip()] = value.strip().lower() in {"1", "true", "yes", "on"}
        if flag_key in flags:
            return flags[flag_key]
        tenant_code = context.get("tenant_code")
        if tenant_code and f"{flag_key}@{tenant_code}" in flags:
            return flags[f"{flag_key}@{tenant_code}"]
        return False


@dataclass(slots=True)
class CircuitState:
    failure_count: int = 0
    opened_until: datetime | None = None


class CircuitBreaker:
    def __init__(self, config_service: ConfigService) -> None:
        self._config = config_service
        self._states: dict[str, CircuitState] = {}

    def execute(
        self,
        name: str,
        func: Callable[[], Any],
        fallback: Callable[[Exception], Any] | Callable[[], Any] | None = None,
    ) -> Any:
        state = self._states.setdefault(name, CircuitState())
        now = utcnow()
        if state.opened_until and state.opened_until > now:
            if fallback is not None:
                return self._run_fallback(fallback, APIError(503, "dependency_unavailable", "Circuit open"))
            raise APIError(status_code=503, code="dependency_unavailable", message="Circuit open")

        try:
            result = func()
        except Exception as exc:
            state.failure_count += 1
            threshold = int(self._config.get("circuit_breaker.failure_threshold", 5))
            if state.failure_count >= threshold:
                timeout = int(self._config.get("circuit_breaker.reset_timeout_seconds", 60))
                state.opened_until = now + timedelta(seconds=timeout)
            if fallback is not None:
                return self._run_fallback(fallback, exc)
            raise

        state.failure_count = 0
        state.opened_until = None
        return result

    @staticmethod
    def _run_fallback(
        fallback: Callable[[Exception], Any] | Callable[[], Any],
        exc: Exception,
    ) -> Any:
        try:
            return fallback(exc)  # type: ignore[misc]
        except TypeError:
            return fallback()  # type: ignore[misc]


@dataclass(slots=True)
class AuditEntry:
    trace_id: str
    tenant_id: UUID | None
    actor_type: Literal["user", "api_client", "system"] = "system"
    actor_user_id: UUID | None = None
    actor_client_id: UUID | None = None
    resource_type: str = ""
    resource_id: str = ""
    action: str = ""
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)


class AuditService:
    def __init__(self, store: Any, trace_service: TraceService, audit_log_repository: Any | None = None) -> None:
        self._store = store
        self._trace_service = trace_service
        self._audit_log_repository = audit_log_repository

    def record(self, entry: AuditEntry) -> dict[str, Any]:
        if not entry.resource_type:
            raise APIError(status_code=500, code="internal_error", message="audit resource_type is required")
        if not entry.action:
            raise APIError(status_code=500, code="internal_error", message="audit action is required")
        trace_id = entry.trace_id or self._trace_service.current_trace_id() or ""
        audit_id = uuid4()
        payload = {
            "audit_id": audit_id,
            "tenant_id": entry.tenant_id,
            "actor_type": entry.actor_type,
            "actor_user_id": entry.actor_user_id,
            "actor_client_id": entry.actor_client_id,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "change_summary": {
                "before": self._sanitize(entry.before),
                "after": self._sanitize(entry.after),
            },
            "trace_id": trace_id,
            "ip_address": None,
            "user_agent": None,
            "created_at": entry.created_at,
        }
        if self._audit_log_repository is not None:
            self._audit_log_repository.save(payload)
        else:
            with self._store.lock():
                self._store.audit_logs[audit_id] = payload
            self._store.persist_audit_log(payload)
        logger.info(
            "audit_recorded %s",
            json.dumps(
                {
                    "trace_id": trace_id,
                    "tenant_id": str(entry.tenant_id) if entry.tenant_id else None,
                    "resource_type": entry.resource_type,
                    "resource_id": entry.resource_id,
                    "action": entry.action,
                },
                default=str,
                sort_keys=True,
            ),
        )
        return payload

    def record_action(
        self,
        *,
        request_context: RequestContext | None,
        resource_type: str,
        resource_id: str,
        action: str,
        trace_id: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_context = request_context or self._trace_service.current_request_context()
        actor_type: Literal["user", "api_client", "system"] = "system"
        actor_user_id: UUID | None = None
        actor_client_id: UUID | None = None
        tenant_id: UUID | None = None
        if request_context is not None:
            actor_type = request_context.actor_type
            actor_user_id = request_context.actor_user_id
            actor_client_id = request_context.actor_client_id
            tenant_id = request_context.tenant_id
        return self.record(
            AuditEntry(
                trace_id=trace_id or (request_context.trace_id if request_context else "") or "",
                tenant_id=tenant_id,
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                actor_client_id=actor_client_id,
                resource_type=resource_type,
                resource_id=resource_id,
                action=action,
                before=before or {},
                after=after or {},
            ),
        )

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, nested_value in value.items():
                if key.lower() in _SENSITIVE_KEYS:
                    sanitized[key] = "***"
                else:
                    sanitized[key] = self._sanitize(nested_value)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        return value
