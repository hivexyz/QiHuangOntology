from __future__ import annotations


def login_admin_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def test_guideline_import_auto_builds_vector_index(client, monkeypatch) -> None:
    token = login_admin_token(client)
    from qihuang_shield.dependencies import ontology_service

    def fake_index_knowledge_assets(*, guide_title, guide_text, kb_version, knowledge_cards):
        return {
            "indexed_count": 3,
            "guide_chunk_count": 1,
            "knowledge_card_count": len(knowledge_cards),
            "documents": [],
        }

    monkeypatch.setattr(ontology_service.vector_search_service, "index_knowledge_assets", fake_index_knowledge_assets)

    response = client.post(
        "/api/v1/ontology/guideline-imports",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "rag-guide.md",
            "source_type": "txt",
            "target_version_code": "kb-rag-001",
            "guide_title": "RAG测试指南",
            "guide_text": "附子：功效：回阳救逆。禁用于孕妇及代茶饮场景。",
        },
    )

    assert response.status_code == 200, response.text
    summary = response.json()["data"]["summary"]
    assert summary["vector_index"]["indexed_count"] == 3


def test_rag_query_endpoint_returns_evidence_pack(client, monkeypatch) -> None:
    token = login_admin_token(client)
    from qihuang_shield.dependencies import vector_search_service

    def fake_rag_search(*, query, top_k):
        return {
            "query": query,
            "top_k": top_k,
            "embedding_model": "fake-model",
            "embedding_dimension": 3,
            "hits": [
                {
                    "doc_id": "knowledge_card_projection::kb-1::mat_001",
                    "text": "实体：附子\n功效：回阳救逆",
                    "score": 0.01,
                    "metadata": {
                        "asset_type": "knowledge_card_projection",
                        "legacy_asset_type": "knowledge_card",
                        "legacy_doc_id": "knowledge_card::kb-1::mat_001",
                        "projection_asset_type": "knowledge_card_projection",
                        "projection_type": "knowledge_card",
                        "standard_name": "附子",
                    },
                    "backend": "memory",
                }
            ],
            "evidence_pack": [
                {
                    "doc_id": "knowledge_card_projection::kb-1::mat_001",
                    "legacy_doc_id": "knowledge_card::kb-1::mat_001",
                    "asset_type": "knowledge_card_projection",
                    "legacy_asset_type": "knowledge_card",
                    "projection_asset_type": "knowledge_card_projection",
                    "projection_type": "knowledge_card",
                    "text": "实体：附子\n功效：回阳救逆",
                    "score": 0.01,
                    "metadata": {
                        "asset_type": "knowledge_card_projection",
                        "legacy_asset_type": "knowledge_card",
                        "legacy_doc_id": "knowledge_card::kb-1::mat_001",
                        "projection_asset_type": "knowledge_card_projection",
                        "projection_type": "knowledge_card",
                        "standard_name": "附子",
                    },
                }
            ],
        }

    monkeypatch.setattr(vector_search_service, "rag_search", fake_rag_search)

    response = client.post(
        "/api/v1/vector-search/rag-query",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={"query": "附子适合什么场景", "top_k": 3},
    )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["query"] == "附子适合什么场景"
    assert len(payload["evidence_pack"]) == 1
    assert payload["evidence_pack"][0]["doc_id"] == "knowledge_card_projection::kb-1::mat_001"
    assert payload["evidence_pack"][0]["legacy_doc_id"] == "knowledge_card::kb-1::mat_001"
    assert payload["evidence_pack"][0]["asset_type"] == "knowledge_card_projection"
    assert payload["evidence_pack"][0]["legacy_asset_type"] == "knowledge_card"
    assert payload["evidence_pack"][0]["projection_asset_type"] == "knowledge_card_projection"
    assert payload["evidence_pack"][0]["projection_type"] == "knowledge_card"
