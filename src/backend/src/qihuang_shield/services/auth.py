from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
import json
import logging
from uuid import UUID

from ..enums import RoleCode
from ..exceptions import APIError
from ..platform_services import SecurityService, TraceService
from ..repositories import ApiClientRepository, AuthTokenRepository, TenantUserRoleRepository, UserRepository
from ..schemas import CurrentUserProfile, LoginResponseData, RequestContext, TenantRole, UserProfile
from ..store import InMemoryStore
from ..utils import utcnow


logger = logging.getLogger(__name__)

ACCESS_TOKEN_TTL_SECONDS = 7200


class AuthService:
    def __init__(
        self,
        store: InMemoryStore,
        *,
        security_service: SecurityService,
        trace_service: TraceService,
        user_repository: UserRepository,
        api_client_repository: ApiClientRepository,
        tenant_user_role_repository: TenantUserRoleRepository,
        auth_token_repository: AuthTokenRepository,
    ) -> None:
        self.store = store
        self.security_service = security_service
        self.trace_service = trace_service
        self.user_repository = user_repository
        self.api_client_repository = api_client_repository
        self.tenant_user_role_repository = tenant_user_role_repository
        self.auth_token_repository = auth_token_repository
        self._failed_login_attempts: dict[str, deque] = defaultdict(deque)
        self._login_rate_limit_window = timedelta(minutes=1)
        self._login_rate_limit_max_attempts = 5

    def login(self, email: str, password: str, *, client_ip: str | None = None) -> LoginResponseData:
        principal = self._rate_limit_key(email=email, client_ip=client_ip)
        self._ensure_login_not_rate_limited(principal)
        trace_id = self.trace_service.current_trace_id()

        user = self.user_repository.get_by_email(email)
        if user is None:
            self._record_failed_login(principal)
            self._log_security_event(
                action="login_failed",
                status="unauthorized",
                trace_id=trace_id,
                email=email,
                client_ip=client_ip,
            )
            raise APIError(status_code=401, code="unauthorized", message="Invalid credentials")

        user_id = user["user_id"]
        if user.get("status") != "active":
            self._record_failed_login(principal)
            self._log_security_event(
                action="login_failed",
                status="user_disabled",
                trace_id=trace_id,
                email=email,
                client_ip=client_ip,
            )
            raise APIError(status_code=401, code="unauthorized", message="User is disabled")
        if not self.security_service.verify_password(password, user.get("password")):
            self._record_failed_login(principal)
            self._log_security_event(
                action="login_failed",
                status="unauthorized",
                trace_id=trace_id,
                email=email,
                client_ip=client_ip,
            )
            raise APIError(status_code=401, code="unauthorized", message="Invalid credentials")

        now = utcnow()
        token = self.security_service.sign(
            {
                "sub": str(user_id),
                "type": "user",
                "iat": int(now.timestamp()),
                "exp": int(now.timestamp()) + ACCESS_TOKEN_TTL_SECONDS,
            },
        )
        user["last_login_at"] = now
        user["updated_at"] = now
        self.user_repository.save(user)
        self.auth_token_repository.save(token, user_id)
        self._clear_failed_login_attempts(principal)
        self._log_security_event(
            action="login_succeeded",
            status="success",
            trace_id=trace_id,
            email=email,
            client_ip=client_ip,
            actor_user_id=str(user_id),
        )
        return LoginResponseData(access_token=token, user=self.get_user_profile(user_id))

    def get_user_profile(self, user_id: UUID) -> UserProfile:
        current_user = self.get_current_user_profile(user_id)
        return UserProfile(
            user_id=current_user.user_id,
            email=current_user.email,
            display_name=current_user.display_name,
            roles=current_user.roles,
        )

    def get_current_user_profile(self, user_id: UUID, tenant_code: str | None = None) -> CurrentUserProfile:
        user = self.user_repository.get(user_id)
        if user is None:
            raise APIError(status_code=404, code="not_found", message="User not found")
        if user.get("status") != "active":
            raise APIError(status_code=401, code="unauthorized", message="User is disabled")

        tenant_roles = self._get_user_tenant_roles(user_id)
        current_tenant = self._select_user_tenant(tenant_roles, tenant_code)
        roles = self._get_roles_for_current_tenant(tenant_roles, current_tenant)
        return CurrentUserProfile(
            user_id=user["user_id"],
            email=user["email"],
            display_name=user["display_name"],
            roles=roles,
            tenant_roles=tenant_roles,
            current_tenant_id=current_tenant.tenant_id if current_tenant else None,
            current_tenant_code=current_tenant.tenant_code if current_tenant else None,
        )

    def get_user_from_token(self, token: str | None, tenant_code: str | None = None) -> CurrentUserProfile:
        user_id = self._resolve_user_id_from_token(token)
        return self.get_current_user_profile(user_id, tenant_code=tenant_code)

    def get_request_context_from_bearer(self, token: str | None, *, tenant_code: str | None = None) -> RequestContext:
        user_id = self._resolve_user_id_from_token(token)

        user = self.get_current_user_profile(user_id, tenant_code=tenant_code)
        return RequestContext(
            trace_id="",
            actor_type="user",
            actor_user_id=user.user_id,
            actor_client_id=None,
            tenant_id=user.current_tenant_id,
            tenant_code=user.current_tenant_code,
            roles=user.roles,
            auth_method="bearer",
            user=user,
        )

    def get_request_context_from_oauth(self, token: str | None, *, tenant_code: str | None = None) -> RequestContext:
        user_id = self._resolve_user_id_from_token(token)
        user = self.get_current_user_profile(user_id, tenant_code=tenant_code)
        return RequestContext(
            trace_id="",
            actor_type="user",
            actor_user_id=user.user_id,
            actor_client_id=None,
            tenant_id=user.current_tenant_id,
            tenant_code=user.current_tenant_code,
            roles=user.roles,
            auth_method="oauth",
            user=user,
        )

    def get_request_context_from_api_key(
        self,
        client_key: str | None,
        client_secret: str | None,
        *,
        tenant_code: str | None = None,
    ) -> RequestContext:
        if not client_key:
            raise APIError(status_code=401, code="unauthorized", message="Missing API key")
        client = self._find_active_client_by_key(client_key)
        self._verify_client_secret(client, client_secret)

        tenant_id = client["tenant_id"]
        resolved_tenant_code = self._resolve_tenant_code(tenant_id)
        if tenant_code and tenant_code != resolved_tenant_code:
            raise APIError(status_code=403, code="forbidden", message="Forbidden")

        return RequestContext(
            trace_id="",
            actor_type="api_client",
            actor_user_id=None,
            actor_client_id=client["client_id"],
            tenant_id=tenant_id,
            tenant_code=resolved_tenant_code,
            roles=[],
            auth_method="api_key",
            user=None,
        )

    def _get_user_tenant_roles(self, user_id: UUID) -> list[TenantRole]:
        items: list[TenantRole] = []
        for membership in self.tenant_user_role_repository.list_active_by_user(user_id):
            items.append(
                TenantRole(
                    tenant_id=membership["tenant_id"],
                    tenant_code=membership["tenant_code"],
                    role=RoleCode(membership["role_code"]),
                )
            )
        items.sort(key=lambda item: (item.tenant_code, str(item.role)))
        return items

    def _select_user_tenant(self, tenant_roles: list[TenantRole], tenant_code: str | None) -> TenantRole | None:
        if not tenant_roles:
            return None
        if tenant_code is None:
            return tenant_roles[0]
        for tenant_role in tenant_roles:
            if tenant_role.tenant_code == tenant_code:
                return tenant_role
        raise APIError(status_code=403, code="forbidden", message="Forbidden")

    @staticmethod
    def _get_roles_for_current_tenant(
        tenant_roles: list[TenantRole],
        current_tenant: TenantRole | None,
    ) -> list[RoleCode]:
        if current_tenant is None:
            return []
        ordered_roles: list[RoleCode] = []
        for tenant_role in tenant_roles:
            if tenant_role.tenant_id != current_tenant.tenant_id:
                continue
            normalized_role = RoleCode(tenant_role.role)
            if normalized_role not in ordered_roles:
                ordered_roles.append(normalized_role)
        return ordered_roles

    @staticmethod
    def _normalize_bearer_token(token: str) -> str:
        value = token.strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        if not value:
            raise APIError(status_code=401, code="unauthorized", message="Missing bearer token")
        return value

    def _resolve_user_id_from_token(self, token: str | None) -> UUID:
        if not token:
            raise APIError(status_code=401, code="unauthorized", message="Missing bearer token")
        normalized_token = self._normalize_bearer_token(token)
        try:
            token_payload = self.security_service.verify(normalized_token)
        except APIError as exc:
            raise APIError(status_code=401, code="unauthorized", message="Invalid bearer token") from exc

        if not isinstance(token_payload, dict):
            raise APIError(status_code=401, code="unauthorized", message="Invalid bearer token")

        stored_user_id = self.auth_token_repository.get_user_id(normalized_token)
        if stored_user_id is not None:
            return stored_user_id

        subject = token_payload.get("sub")
        try:
            user_id = UUID(str(subject))
        except (TypeError, ValueError) as exc:
            raise APIError(status_code=401, code="unauthorized", message="Invalid bearer token") from exc

        return user_id

    def _find_active_client_by_key(self, client_key: str) -> dict:
        client = self.api_client_repository.get_by_key(client_key)
        if client is not None:
            if client.get("status") != "active":
                raise APIError(status_code=401, code="unauthorized", message="API client is disabled")
            return client
        raise APIError(status_code=401, code="unauthorized", message="Invalid API key")

    def _verify_client_secret(self, client: dict, client_secret: str | None) -> None:
        if not client_secret:
            raise APIError(status_code=401, code="unauthorized", message="Missing API secret")

        stored_secret_hash = str(client.get("client_secret_hash") or "")
        if not self.security_service.verify_password(client_secret, stored_secret_hash):
            raise APIError(status_code=401, code="unauthorized", message="Invalid API secret")

    def _log_security_event(
        self,
        *,
        action: str,
        status: str,
        trace_id: str | None,
        email: str | None = None,
        client_ip: str | None = None,
        actor_user_id: str | None = None,
    ) -> None:
        logger.info(
            "security_event %s",
            json.dumps(
                {
                    "module": "m01_auth",
                    "action": action,
                    "status": status,
                    "trace_id": trace_id,
                    "tenant_id": None,
                    "latency_ms": None,
                    "email": email,
                    "client_ip": client_ip,
                    "actor_user_id": actor_user_id,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
        )

    def _resolve_tenant_code(self, tenant_id: UUID) -> str | None:
        tenant = self.store.tenants.get(tenant_id)
        if tenant is None:
            return None
        return tenant.get("tenant_code")

    def _ensure_login_not_rate_limited(self, principal: str) -> None:
        attempts = self._failed_login_attempts[principal]
        self._prune_expired_attempts(attempts)
        if len(attempts) >= self._login_rate_limit_max_attempts:
            raise APIError(status_code=429, code="rate_limited", message="Too many login attempts")

    def _record_failed_login(self, principal: str) -> None:
        attempts = self._failed_login_attempts[principal]
        self._prune_expired_attempts(attempts)
        attempts.append(utcnow())

    def _clear_failed_login_attempts(self, principal: str) -> None:
        self._failed_login_attempts.pop(principal, None)

    def _prune_expired_attempts(self, attempts: deque) -> None:
        cutoff = utcnow() - self._login_rate_limit_window
        while attempts and attempts[0] < cutoff:
            attempts.popleft()

    @staticmethod
    def _rate_limit_key(*, email: str, client_ip: str | None) -> str:
        if client_ip:
            return f"{email.lower()}::{client_ip}"
        return email.lower()
