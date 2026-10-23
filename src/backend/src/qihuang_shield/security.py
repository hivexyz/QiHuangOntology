from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import UUID

from .enums import RoleCode
from .exceptions import APIError
from .schemas import PermissionDecision, RequestContext
from .services.auth import AuthService
from .store import InMemoryStore


@dataclass(slots=True)
class PermissionRule:
    action: str
    resource: str
    allowed_roles: set[RoleCode]
    allow_api_client: bool = False


class AuthContextService:
    def __init__(self, auth_service: AuthService, store: InMemoryStore) -> None:
        self.auth_service = auth_service
        self.store = store

    def resolve(
        self,
        *,
        authorization: str | None,
        tenant_code: str | None,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> RequestContext:
        if authorization:
            scheme, _, credential = authorization.partition(" ")
            normalized_scheme = scheme.lower()
            if normalized_scheme == "bearer":
                return self.auth_service.get_request_context_from_bearer(
                    credential.strip(),
                    tenant_code=tenant_code,
                )
            if normalized_scheme == "oauth":
                return self.auth_service.get_request_context_from_oauth(
                    credential.strip(),
                    tenant_code=tenant_code,
                )
            if normalized_scheme == "apikey":
                client_key, client_secret = self._split_api_key_credential(credential)
                return self.auth_service.get_request_context_from_api_key(
                    client_key,
                    client_secret,
                    tenant_code=tenant_code,
                )
            raise APIError(status_code=401, code="unauthorized", message="Unsupported authorization scheme")

        if api_key:
            return self.auth_service.get_request_context_from_api_key(
                api_key,
                api_secret,
                tenant_code=tenant_code,
            )

        raise APIError(status_code=401, code="unauthorized", message="Missing bearer token")

    @staticmethod
    def _split_api_key_credential(credential: str) -> tuple[str, str | None]:
        value = credential.strip()
        if not value:
            raise APIError(status_code=401, code="unauthorized", message="Missing API key credential")
        client_key, separator, client_secret = value.partition(":")
        if not separator:
            raise APIError(status_code=401, code="unauthorized", message="Invalid API key credential")
        return client_key.strip(), client_secret.strip() or None


class PermissionService:
    def __init__(self) -> None:
        self._rules: dict[tuple[str, str], PermissionRule] = {}
        self._register_defaults()

    def check(
        self,
        context: RequestContext,
        *,
        action: str,
        resource: str,
        tenant_id: UUID | None = None,
    ) -> PermissionDecision:
        rule = self._rules.get((resource, action))
        if rule is None:
            return PermissionDecision(
                allowed=True,
                action=action,
                resource=resource,
                reason="no explicit permission rule configured",
            )

        if context.actor_type == "api_client" and not rule.allow_api_client:
            raise APIError(status_code=403, code="forbidden", message="API client is not allowed to access this resource")

        if context.actor_type == "api_client" and rule.allow_api_client:
            self._check_tenant_scope(context, tenant_id)
            return PermissionDecision(allowed=True, action=action, resource=resource)

        current_roles = {RoleCode(role) for role in context.roles}
        if RoleCode.ADMIN in current_roles:
            self._check_tenant_scope(context, tenant_id)
            return PermissionDecision(allowed=True, action=action, resource=resource)

        if not current_roles.intersection(rule.allowed_roles):
            raise APIError(status_code=403, code="forbidden", message="Forbidden")

        self._check_tenant_scope(context, tenant_id)
        return PermissionDecision(allowed=True, action=action, resource=resource)

    def register(
        self,
        *,
        resource: str,
        action: str,
        allowed_roles: Iterable[RoleCode],
        allow_api_client: bool = False,
    ) -> None:
        self._rules[(resource, action)] = PermissionRule(
            action=action,
            resource=resource,
            allowed_roles=set(allowed_roles),
            allow_api_client=allow_api_client,
        )

    @staticmethod
    def _check_tenant_scope(context: RequestContext, tenant_id: UUID | None) -> None:
        if tenant_id is None or context.tenant_id is None:
            return
        if context.tenant_id != tenant_id:
            raise APIError(status_code=403, code="forbidden", message="Forbidden")

    def _register_defaults(self) -> None:
        self.register(resource="rule", action="read", allowed_roles={RoleCode.ADMIN, RoleCode.OPERATOR, RoleCode.AUDITOR})
        self.register(resource="rule", action="write", allowed_roles={RoleCode.ADMIN, RoleCode.OPERATOR})
        self.register(resource="rule", action="publish", allowed_roles={RoleCode.ADMIN})
        self.register(resource="policy", action="read", allowed_roles={RoleCode.ADMIN, RoleCode.OPERATOR, RoleCode.AUDITOR})
        self.register(resource="policy", action="write", allowed_roles={RoleCode.ADMIN, RoleCode.OPERATOR})
        self.register(resource="policy", action="publish", allowed_roles={RoleCode.ADMIN})
        self.register(resource="ontology", action="read", allowed_roles={RoleCode.ADMIN, RoleCode.ONTOLOGY_ADMIN, RoleCode.EXPERT})
        self.register(resource="ontology", action="write", allowed_roles={RoleCode.ADMIN, RoleCode.ONTOLOGY_ADMIN})
        self.register(resource="ontology", action="publish", allowed_roles={RoleCode.ADMIN, RoleCode.ONTOLOGY_ADMIN})
