from __future__ import annotations


def login_admin_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def test_vector_health_endpoint_returns_status(client) -> None:
    token = login_admin_token(client)
    response = client.get(
        "/api/v1/vector-search/health",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert "embedding_ready" in payload
    assert "vector_store" in payload


def test_vector_upsert_and_query_with_stubbed_embedding(client, monkeypatch) -> None:
    token = login_admin_token(client)
    from qihuang_shield.dependencies import vector_search_service, vector_store_service

    vector_store_service._memory_vectors.clear()

    def fake_embed_text(text: str):
        class R:
            vector = [0.1, 0.2, 0.3]
            model = "fake-embedding-model"
            dimension = 3
        return R()

    monkeypatch.setattr(vector_search_service._embedding_service, "embed_text", fake_embed_text)

    upsert = client.post(
        "/api/v1/vector-search/documents",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={"doc_id": "doc-001", "text": "附子用于回阳救逆", "metadata": {"source": "test"}},
    )
    assert upsert.status_code == 200, upsert.text
    assert upsert.json()["data"]["doc_id"] == "doc-001"
    assert upsert.json()["data"]["embedding_dimension"] == 3

    query = client.post(
        "/api/v1/vector-search/query",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={"query": "回阳救逆", "top_k": 3},
    )
    assert query.status_code == 200, query.text
    hits = query.json()["data"]["hits"]
    assert len(hits) >= 1
    assert hits[0]["doc_id"] == "doc-001"
    assert hits[0]["backend"] in {"memory", "milvus"}
