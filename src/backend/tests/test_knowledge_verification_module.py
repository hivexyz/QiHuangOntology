from __future__ import annotations


def _login_admin(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"}


def test_concept_search_finds_standard_name_and_alias(client) -> None:
    token = _login_admin(client)
    standard_response = client.get(
        "/api/v1/ontology-base/concept-search",
        headers=_headers(token),
        params={"query": "四君子汤", "concept_type": "Formula"},
    )
    alias_response = client.get(
        "/api/v1/ontology-base/concept-search",
        headers=_headers(token),
        params={"query": "脾气虚证", "concept_type": "Pattern"},
    )

    assert standard_response.status_code == 200, standard_response.text
    assert alias_response.status_code == 200, alias_response.text
    standard_items = standard_response.json()["data"]
    alias_items = alias_response.json()["data"]
    assert any(item["concept"]["standard_name"] == "四君子汤" for item in standard_items)
    pattern = next(item for item in alias_items if item["concept"]["standard_name"] == "脾虚")
    assert pattern["matched_text"] == "脾气虚证"
    assert pattern["match_type"] == "alias"
    assert pattern["assertion_count"] > 0
    assert pattern["evidence_count"] > 0


def test_concept_verification_returns_assertions_conditions_evidence_and_related_concepts(client) -> None:
    token = _login_admin(client)
    search_response = client.get(
        "/api/v1/ontology-base/concept-search",
        headers=_headers(token),
        params={"query": "四君子汤", "concept_type": "Formula"},
    )
    concept_id = next(
        item["concept"]["entity_id"]
        for item in search_response.json()["data"]
        if item["concept"]["standard_name"] == "四君子汤"
    )

    response = client.get(
        f"/api/v1/ontology-base/concepts/{concept_id}/verification",
        headers=_headers(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["concept"]["entity_id"] == concept_id
    assert data["release_code"] == data["concept"]["kb_version"]
    assert data["assertions"]
    assert data["evidence_sources"]
    predicates = {item["assertion"]["predicate_type"] for item in data["assertions"]}
    assert "REALIZED_BY_FORMULA" in predicates or "HAS_INGREDIENT" in predicates
    assert any(item["standard_name"] in {"人参", "益气健脾法"} for item in data["related_concepts"])


def test_concept_verification_respects_kb_version_filter(client) -> None:
    token = _login_admin(client)
    search_response = client.get(
        "/api/v1/ontology-base/concept-search",
        headers=_headers(token),
        params={"query": "四君子汤", "concept_type": "Formula"},
    )
    concept_id = next(
        item["concept"]["entity_id"]
        for item in search_response.json()["data"]
        if item["concept"]["standard_name"] == "四君子汤"
    )

    ok_response = client.get(
        f"/api/v1/ontology-base/concepts/{concept_id}/verification",
        headers=_headers(token),
        params={"kb_version": "knowledge-content-v0.1"},
    )
    missing_response = client.get(
        f"/api/v1/ontology-base/concepts/{concept_id}/verification",
        headers=_headers(token),
        params={"kb_version": "kb-not-this-release"},
    )

    assert ok_response.status_code == 200, ok_response.text
    assert missing_response.status_code == 404, missing_response.text
