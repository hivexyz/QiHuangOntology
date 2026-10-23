from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from qihuang_shield.dependencies import auth_service, security_service, store
from qihuang_shield.exceptions import APIError
from qihuang_shield.platform_services import ConfigService, SecurityService
from qihuang_shield.utils import utcnow


def test_demo_seeded_credentials_are_hashed_and_still_authenticate(client) -> None:
    user_records = list(store.users.values())
    api_client = next(iter(store.api_clients.values()))

    assert user_records
    assert all(record["password"].startswith("scrypt$") for record in user_records)
    assert api_client["client_secret_hash"].startswith("scrypt$")

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "reviewer@example.com", "password": "password123"},
    )
    assert login_response.status_code == 200, login_response.text

    context = auth_service.get_request_context_from_api_key(
        "demo-client",
        "demo-secret",
        tenant_code="tenant_demo",
    )
    assert context.actor_type == "api_client"
    assert context.auth_method == "api_key"


@pytest.mark.parametrize("stored_value", ["password123", "password123-hash", "password123_hash"])
def test_password_verification_rejects_non_scrypt_values(stored_value: str) -> None:
    assert security_service.verify_password("password123", stored_value) is False


@pytest.mark.parametrize("client_secret", ["demo-secret-hash", "demo-secret_hash"])
def test_api_client_auth_rejects_secret_markers(client_secret: str) -> None:
    with pytest.raises(APIError) as exc_info:
        auth_service.get_request_context_from_api_key("demo-client", client_secret)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "unauthorized"


def test_login_token_contains_issue_and_expiry_times(client) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "reviewer@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text

    payload = security_service.verify(response.json()["data"]["access_token"])
    assert isinstance(payload, dict)
    assert isinstance(payload["iat"], int)
    assert isinstance(payload["exp"], int)
    assert payload["exp"] > payload["iat"]


def test_security_verify_rejects_missing_and_expired_exp() -> None:
    without_exp = security_service.sign({"sub": "user-id", "type": "user"})
    with pytest.raises(APIError, match="Invalid signature token"):
        security_service.verify(without_exp)

    expired = security_service.sign(
        {
            "sub": "user-id",
            "type": "user",
            "iat": int((utcnow() - timedelta(minutes=2)).timestamp()),
            "exp": int((utcnow() - timedelta(seconds=1)).timestamp()),
        },
    )
    with pytest.raises(APIError, match="Expired signature token"):
        security_service.verify(expired)


def test_expired_issued_token_is_not_rescued_by_token_repository() -> None:
    user_id = next(iter(store.users))
    expired = security_service.sign(
        {
            "sub": str(user_id),
            "type": "user",
            "iat": int((utcnow() - timedelta(minutes=2)).timestamp()),
            "exp": int((utcnow() - timedelta(seconds=1)).timestamp()),
        },
    )
    auth_service.auth_token_repository.save(expired, user_id)

    with pytest.raises(APIError) as exc_info:
        auth_service.get_request_context_from_bearer(expired)

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "unauthorized"


def test_security_verify_accepts_valid_expiring_token() -> None:
    now = utcnow()
    token = security_service.sign(
        {
            "sub": "user-id",
            "type": "user",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
    )

    payload = security_service.verify(token)
    assert payload["sub"] == "user-id"
    assert payload["type"] == "user"


def test_non_demo_secret_does_not_fall_back_to_development_key(monkeypatch) -> None:
    monkeypatch.delenv("QHS_SECURITY_SECRET_KEY", raising=False)
    config_service = ConfigService(SimpleNamespace(allow_insecure_dev_secret=False))
    service = SecurityService(config_service)

    with pytest.raises(RuntimeError, match="QHS_SECURITY_SECRET_KEY"):
        service.sign({"exp": int((utcnow() + timedelta(minutes=5)).timestamp())})
