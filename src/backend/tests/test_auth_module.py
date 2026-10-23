from __future__ import annotations

from qihuang_shield.dependencies import snapshot_provider, store


LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


def login_and_get_token(client, email: str = "reviewer@example.com", password: str = "password123") -> str:
    response = client.post(LOGIN_URL, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def test_login_success_returns_envelope_and_trace_header(client) -> None:
    response = client.post(
        LOGIN_URL,
        headers={"X-Trace-Id": "trc_test_login_001"},
        json={"email": "reviewer@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["trace_id"] == "trc_test_login_001"
    assert response.headers["X-Trace-Id"] == "trc_test_login_001"
    assert payload["data"]["token_type"] == "Bearer"
    assert payload["data"]["expires_in"] == 7200
    assert payload["data"]["user"]["email"] == "reviewer@example.com"
    assert payload["data"]["user"]["roles"] == ["reviewer"]


def test_login_invalid_password_returns_unauthorized(client) -> None:
    response = client.post(LOGIN_URL, json={"email": "reviewer@example.com", "password": "wrong"})

    assert response.status_code == 401
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "unauthorized"


def test_login_rate_limit_after_repeated_failures(client) -> None:
    for _ in range(5):
        response = client.post(LOGIN_URL, json={"email": "reviewer@example.com", "password": "wrong"})
        assert response.status_code == 401

    response = client.post(LOGIN_URL, json={"email": "reviewer@example.com", "password": "wrong"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_auth_me_returns_current_user_and_tenant_roles(client) -> None:
    token = login_and_get_token(client)

    response = client.get(
        ME_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Code": "tenant_demo",
            "X-Trace-Id": "trc_test_me_001",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == "trc_test_me_001"
    assert response.headers["X-Trace-Id"] == "trc_test_me_001"
    assert payload["data"]["email"] == "reviewer@example.com"
    assert payload["data"]["current_tenant_code"] == "tenant_demo"
    assert payload["data"]["roles"] == ["reviewer"]
    assert payload["data"]["tenant_roles"][0]["tenant_code"] == "tenant_demo"
    assert payload["data"]["tenant_roles"][0]["role"] == "reviewer"


def test_auth_me_requires_valid_token(client) -> None:
    missing = client.get(ME_URL)
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "unauthorized"

    invalid = client.get(ME_URL, headers={"Authorization": "Bearer invalid-token"})
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "unauthorized"
def test_active_snapshot_uses_projection_read_model() -> None:
    snapshot = snapshot_provider.get_active_kb_snapshot()

    assert snapshot is not None
    assert snapshot["knowledge_card_projections"] == store.knowledge_card_projections
    assert snapshot["knowledge_cards"] == store.knowledge_card_projections
