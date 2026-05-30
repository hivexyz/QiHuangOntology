from __future__ import annotations

from fastapi import Header

from .config import get_settings
from .db_store import DatabaseBackedStore
from .exceptions import APIError
from .services.auth import AuthService
from .services.moderation import ModerationService
from .services.ontology import OntologyService
from .services.policies import PolicyService
from .services.reports import ReportService
from .services.review import ReviewService
from .services.rules import RuleService
from .store import InMemoryStore

settings = get_settings()
store = DatabaseBackedStore(settings) if settings.use_database else InMemoryStore()
auth_service = AuthService(store)
moderation_service = ModerationService(store)
review_service = ReviewService(store, moderation_service)
rule_service = RuleService(store)
policy_service = PolicyService(store)
ontology_service = OntologyService(store)
report_service = ReportService(store)


def get_auth_service() -> AuthService:
    return auth_service


def get_moderation_service() -> ModerationService:
    return moderation_service


def get_review_service() -> ReviewService:
    return review_service


def get_rule_service() -> RuleService:
    return rule_service


def get_policy_service() -> PolicyService:
    return policy_service


def get_ontology_service() -> OntologyService:
    return ontology_service


def get_report_service() -> ReportService:
    return report_service


def get_store() -> InMemoryStore:
    return store


def get_current_user(authorization: str | None = Header(default=None)):
    if authorization is None:
        raise APIError(status_code=401, code="unauthorized", message="Missing bearer token")
    return auth_service.get_user_from_token(authorization)
