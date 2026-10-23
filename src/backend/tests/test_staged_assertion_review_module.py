from __future__ import annotations

from uuid import UUID

from qihuang_shield.dependencies import ontology_service, store


def _login_admin(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"}


def _import_guideline(client, monkeypatch, version_code: str) -> tuple[str, str, list[str]]:
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    token = _login_admin(client)
    response = client.post(
        "/api/v1/ontology/guideline-imports",
        headers=_headers(token),
        json={
            "source_uri": f"{version_code}.md",
            "source_type": "txt",
            "target_version_code": version_code,
            "guide_title": "断言审核测试",
            "guide_text": "附子：功效：回阳救逆。禁用于孕妇及代茶饮场景。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    staged_assertions = store.import_jobs[UUID(import_job_id)]["staged_snapshot"]["ontology_assertions"]
    assertion_ids = sorted(staged_assertions)
    assert len(assertion_ids) >= 2
    return token, import_job_id, assertion_ids


def test_import_governance_exposes_staged_assertions(client, monkeypatch) -> None:
    token, import_job_id, assertion_ids = _import_guideline(client, monkeypatch, "kb-assert-review-governance-001")

    response = client.get(
        f"/api/v1/ontology/import-jobs/{import_job_id}/governance",
        headers=_headers(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    returned_ids = {item["assertion"]["assertion_id"] for item in data["staged_assertions"]}
    assert set(assertion_ids).issubset(returned_ids)
    assert all(item["evidence_sources"] for item in data["staged_assertions"])


def test_rejected_staged_assertion_is_excluded_from_publish(client, monkeypatch) -> None:
    token, import_job_id, assertion_ids = _import_guideline(client, monkeypatch, "kb-assert-review-reject-001")
    rejected_id = assertion_ids[0]

    review_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/assertions/{rejected_id}/review",
        headers=_headers(token),
        json={"status": "rejected", "reason": "证据不能支持该断言", "operator_id": "curator_001"},
    )
    assert review_response.status_code == 200, review_response.text
    reviewed = review_response.json()["data"]
    assert reviewed["assertion"]["review_status"] == "rejected"
    assert reviewed["assertion"]["review_reason"] == "证据不能支持该断言"
    staged_snapshot = store.import_jobs[UUID(import_job_id)]["staged_snapshot"]
    assert staged_snapshot["ontology_assertions"][rejected_id]["review_status"] == "rejected"
    assert any(
        change["object_id"] == rejected_id and change["to_version"] == "rejected"
        for change in staged_snapshot["change_records"].values()
    )

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers=_headers(token),
    )
    assert publish_response.status_code == 200, publish_response.text
    assert rejected_id not in store.ontology_assertions
    assert any(
        assertion_id in store.ontology_assertions
        for assertion_id in assertion_ids
        if assertion_id != rejected_id
    )


def test_accepted_staged_assertion_is_published_with_review_metadata(client, monkeypatch) -> None:
    token, import_job_id, assertion_ids = _import_guideline(client, monkeypatch, "kb-assert-review-accept-001")
    accepted_id = assertion_ids[0]

    review_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/assertions/{accepted_id}/review",
        headers=_headers(token),
        json={"status": "accepted", "reason": "证据支持该断言", "operator_id": "curator_001"},
    )
    assert review_response.status_code == 200, review_response.text
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers=_headers(token),
    )
    assert publish_response.status_code == 200, publish_response.text
    assert store.ontology_assertions[accepted_id]["review_status"] == "accepted"
    assert store.ontology_assertions[accepted_id]["review_reason"] == "证据支持该断言"


def test_review_missing_staged_assertion_returns_not_found(client, monkeypatch) -> None:
    token, import_job_id, _ = _import_guideline(client, monkeypatch, "kb-assert-review-missing-001")
    response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/assertions/missing-assertion/review",
        headers=_headers(token),
        json={"status": "rejected", "reason": "不存在的断言", "operator_id": "curator_001"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
