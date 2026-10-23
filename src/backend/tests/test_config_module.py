from __future__ import annotations

from qihuang_shield.config import get_settings


def login_admin_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def test_settings_load_extended_env_config() -> None:
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.postgres_dsn.startswith("postgresql://postgres:12345678@localhost:5432/")
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == 5432
    assert settings.openai_base_url == "http://localhost:1234/v1"
    assert settings.openai_model == "qwen/qwen3-4b"
    assert settings.openai_embedding_model == "text-embedding-bge-m3"
    assert settings.openai_embedding_dimension == 1024
    assert settings.milvus_host == "localhost"
    assert settings.milvus_port == 19530
    assert settings.milvus_collection_name == "vectors"
    assert settings.embedding_ready is True
    assert settings.openai_chat_ready is True
    assert settings.milvus_ready is True
    assert settings.llm_base_url == "http://localhost:1234/v1"


def test_config_check_endpoint_returns_masked_runtime_snapshot(client) -> None:
    token = login_admin_token(client)

    response = client.get(
        "/api/v1/ontology/config-check",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["postgres"]["dsn_configured"] is True
    assert "***" in payload["postgres"]["dsn_masked"]
    assert payload["openai_chat"]["ready"] is True
    assert payload["embedding"]["ready"] is True
    assert payload["milvus"]["ready"] is True
    assert payload["qhs_llm"]["base_url"] == "http://localhost:1234/v1"
