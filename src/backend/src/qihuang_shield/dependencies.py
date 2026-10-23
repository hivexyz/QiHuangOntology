from __future__ import annotations

from typing import Callable

from fastapi import Depends, Header, Request

from .config import get_settings
from .db_store import DatabaseBackedStore
from .exceptions import APIError
from .platform_services import (
    AuditService,
    CacheControlService,
    CircuitBreaker,
    ConfigService,
    ExceptionMapper,
    FeatureFlagService,
    ResponseEnvelopeFactory,
    SecurityService,
    TraceService,
)
from .repositories import (
    M12CacheProvider,
    StoreBackedApiClientRepository,
    StoreBackedAuditLogRepository,
    StoreBackedAuthTokenRepository,
    StoreBackedSnapshotProvider,
    StoreBackedTenantUserRoleRepository,
    StoreBackedUnitOfWork,
    StoreBackedUserRepository,
)
from .security import AuthContextService, PermissionService
from .services.auth import AuthService
from .services.ontology import OntologyService
from .services.ontology_base import OntologyBaseService
from .services.ontology_base_validator import OntologyBaseValidator
from .services.vector_search import EmbeddingService, VectorSearchService, VectorStoreService
from .services.policies import PolicyService
from .services.rules import RuleService
from .store import InMemoryStore

settings = get_settings()
trace_service = TraceService()
config_service = ConfigService(settings)
security_service = SecurityService(config_service)
exception_mapper = ExceptionMapper()
response_envelope_factory = ResponseEnvelopeFactory(trace_service)
cache_control_service = CacheControlService(config_service)
feature_flag_service = FeatureFlagService(config_service)
circuit_breaker = CircuitBreaker(config_service)
store = DatabaseBackedStore(settings) if settings.use_database else InMemoryStore(seed_demo_data=settings.enable_demo_seed)
unit_of_work = StoreBackedUnitOfWork(store)
user_repository = StoreBackedUserRepository(store)
api_client_repository = StoreBackedApiClientRepository(store)
tenant_user_role_repository = StoreBackedTenantUserRoleRepository(store)
auth_token_repository = StoreBackedAuthTokenRepository(store)
audit_log_repository = StoreBackedAuditLogRepository(store)
cache_provider = M12CacheProvider(cache_control_service)
snapshot_provider = StoreBackedSnapshotProvider(store=store, cache_provider=cache_provider)
audit_service = AuditService(store, trace_service, audit_log_repository=audit_log_repository)
auth_service = AuthService(
    store,
    security_service=security_service,
    trace_service=trace_service,
    user_repository=user_repository,
    api_client_repository=api_client_repository,
    tenant_user_role_repository=tenant_user_role_repository,
    auth_token_repository=auth_token_repository,
)
auth_context_service = AuthContextService(auth_service, store)
permission_service = PermissionService()
embedding_service = EmbeddingService(settings)
vector_store_service = VectorStoreService(settings, store)
vector_search_service = VectorSearchService(embedding_service, vector_store_service)
rule_service = RuleService(store)
policy_service = PolicyService(store)
ontology_service = OntologyService(store, vector_search_service=vector_search_service)
ontology_base_service = OntologyBaseService(store)
ontology_base_validator = OntologyBaseValidator(store)


def get_auth_service() -> AuthService:
    return auth_service


def get_trace_service() -> TraceService:
    return trace_service


def get_unit_of_work() -> StoreBackedUnitOfWork:
    return unit_of_work


def get_user_repository() -> StoreBackedUserRepository:
    return user_repository


def get_api_client_repository() -> StoreBackedApiClientRepository:
    return api_client_repository


def get_tenant_user_role_repository() -> StoreBackedTenantUserRoleRepository:
    return tenant_user_role_repository


def get_auth_token_repository() -> StoreBackedAuthTokenRepository:
    return auth_token_repository


def get_audit_log_repository() -> StoreBackedAuditLogRepository:
    return audit_log_repository


def get_cache_provider() -> M12CacheProvider:
    return cache_provider


def get_snapshot_provider() -> StoreBackedSnapshotProvider:
    return snapshot_provider


def get_config_service() -> ConfigService:
    return config_service


def get_security_service() -> SecurityService:
    return security_service


def get_exception_mapper() -> ExceptionMapper:
    return exception_mapper


def get_response_envelope_factory() -> ResponseEnvelopeFactory:
    return response_envelope_factory


def get_audit_service() -> AuditService:
    return audit_service


def get_cache_control_service() -> CacheControlService:
    return cache_control_service


def get_feature_flag_service() -> FeatureFlagService:
    return feature_flag_service


def get_circuit_breaker() -> CircuitBreaker:
    return circuit_breaker


def get_auth_context_service() -> AuthContextService:
    return auth_context_service


def get_permission_service() -> PermissionService:
    return permission_service


def get_rule_service() -> RuleService:
    return rule_service


def get_policy_service() -> PolicyService:
    return policy_service


def get_ontology_service() -> OntologyService:
    return ontology_service


def get_ontology_base_service() -> OntologyBaseService:
    return ontology_base_service


def get_ontology_base_validator() -> OntologyBaseValidator:
    return ontology_base_validator


def get_store() -> InMemoryStore:
    return store


async def get_request_context(
    request: Request,
    authorization: str | None = Header(default=None),
    x_tenant_code: str | None = Header(default=None, alias="X-Tenant-Code"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_api_secret: str | None = Header(default=None, alias="X-API-Secret"),
    context_service: AuthContextService = Depends(get_auth_context_service),
    trace: TraceService = Depends(get_trace_service),
):
    existing_context = getattr(request.state, "request_context", None)
    if existing_context is not None:
        return existing_context

    context = context_service.resolve(
        authorization=authorization,
        tenant_code=x_tenant_code,
        api_key=x_api_key,
        api_secret=x_api_secret,
    )
    context.trace_id = request.state.trace_id
    request.state.request_context = context
    token = trace.bind_request_context(context)
    request.state.request_context_token = token
    return context


def get_current_user(request_context=Depends(get_request_context)):
    if request_context.actor_type != "user" or request_context.user is None:
        raise APIError(status_code=401, code="unauthorized", message="User authentication is required")
    return request_context.user


def require_permission(resource: str, action: str) -> Callable:
    def _dependency(
        request_context=Depends(get_request_context),
        permissions: PermissionService = Depends(get_permission_service),
    ):
        permissions.check(request_context, action=action, resource=resource, tenant_id=request_context.tenant_id)
        return request_context

    return _dependency


def get_vector_search_service() -> VectorSearchService:
    return vector_search_service
