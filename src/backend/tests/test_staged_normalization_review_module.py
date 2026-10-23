from __future__ import annotations

from uuid import UUID

from qihuang_shield.dependencies import ontology_service, store


GOVERNANCE_URL = "/api/v1/ontology/import-jobs/{}/governance"
STAGED_REVIEW_URL = "/api/v1/ontology/import-jobs/{}/normalizations/{}/review"


def login_admin_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def import_unresolved_guideline(client, monkeypatch, version_code: str) -> tuple[str, str, dict]:
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    token = login_admin_token(client)
    response = client.post(
        "/api/v1/ontology/guideline-imports",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": f"{version_code}.md",
            "source_type": "txt",
            "target_version_code": version_code,
            "guide_title": "阶段归一评审测试",
            "guide_text": "附子：证候：月光虚证；禁用于孕妇。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    job = store.import_jobs[UUID(import_job_id)]
    decision = next(
        item
        for item in job["staged_snapshot"]["normalization_decisions"].values()
        if item["status"] == "unresolved"
    )
    return token, import_job_id, decision


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"}


def test_staged_resolution_updates_governance_without_global_publish(client, monkeypatch) -> None:
    token, import_job_id, decision = import_unresolved_guideline(
        client, monkeypatch, "kb-staged-review-resolve-001"
    )
    governance_response = client.get(GOVERNANCE_URL.format(import_job_id), headers=headers(token))
    assert governance_response.status_code == 200, governance_response.text
    before = governance_response.json()["data"]
    normalization_issues = [
        issue for issue in before["issues"] if issue["object_type"] == "normalization_decision"
    ]
    assert len(normalization_issues) == 1
    assert normalization_issues[0]["mention_id"] == decision["mention_id"]
    assert normalization_issues[0]["surface_text"] == "月光虚证"
    assert normalization_issues[0]["candidate_list"] == []
    assert normalization_issues[0]["resolved_concept_id"] is None
    assert normalization_issues[0]["canonical_name"] is None

    review_response = client.post(
        STAGED_REVIEW_URL.format(import_job_id, decision["decision_id"]),
        headers=headers(token),
        json={
            "status": "resolved",
            "resolved_concept_id": "mat_001",
            "create_alias": True,
            "reason": "人工归一到附子",
            "operator_id": "curator_001",
        },
    )
    assert review_response.status_code == 200, review_response.text
    reviewed = review_response.json()["data"]
    assert reviewed["status"] == "resolved"
    assert reviewed["resolved_concept_id"] == "mat_001"
    assert reviewed["canonical_name"] == "附子"
    assert reviewed["candidate_list"] == [
        {
            "concept_id": "mat_001",
            "canonical_name": "附子",
            "concept_type": store.ontology_entities["mat_001"]["label"],
            "score": 1.0,
        }
    ]

    job = store.import_jobs[UUID(import_job_id)]
    staged_snapshot = job["staged_snapshot"]
    staged_decision = staged_snapshot["normalization_decisions"][decision["decision_id"]]
    assert staged_decision["status"] == "resolved"
    staged_alias = next(
        alias
        for alias in staged_snapshot["concept_aliases"].values()
        if alias.get("alias_text") == "月光虚证"
        and alias.get("concept_entity_id") == "mat_001"
        and alias.get("alias_type") == "reviewed_normalization_alias"
    )
    assert staged_alias["status"] == "draft"
    assert decision["decision_id"] not in store.normalization_decisions
    assert staged_alias["alias_id"] not in store.concept_aliases
    assert any(
        change["object_id"] == decision["decision_id"]
        and change["to_version"] == "resolved"
        for change in staged_snapshot["change_records"].values()
    )
    assert not any(
        change["object_id"] == decision["decision_id"]
        for change in store.change_records.values()
    )

    after_response = client.get(GOVERNANCE_URL.format(import_job_id), headers=headers(token))
    assert after_response.status_code == 200, after_response.text
    after = after_response.json()["data"]
    assert not [issue for issue in after["issues"] if issue["object_type"] == "normalization_decision"]
    assert after["summary"]["issue_count"] == len(after["issues"])
    assert after["summary"]["issue_count"] == before["summary"]["issue_count"] - 1

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers=headers(token),
    )
    assert publish_response.status_code == 200, publish_response.text
    assert store.normalization_decisions[decision["decision_id"]]["status"] == "resolved"
    assert store.concept_aliases[staged_alias["alias_id"]]["status"] == "published"
    assert any(
        change["object_id"] == decision["decision_id"]
        and change["to_version"] == "resolved"
        for change in store.change_records.values()
    )


def test_staged_rejection_is_reflected_and_published_as_rejected(client, monkeypatch) -> None:
    token, import_job_id, decision = import_unresolved_guideline(
        client, monkeypatch, "kb-staged-review-reject-001"
    )
    review_response = client.post(
        STAGED_REVIEW_URL.format(import_job_id, decision["decision_id"]),
        headers=headers(token),
        json={
            "status": "rejected",
            "reason": "确认该提及不纳入本次知识库",
            "operator_id": "curator_002",
        },
    )
    assert review_response.status_code == 200, review_response.text
    assert review_response.json()["data"]["status"] == "rejected"

    staged_decision = store.import_jobs[UUID(import_job_id)]["staged_snapshot"]["normalization_decisions"][
        decision["decision_id"]
    ]
    assert staged_decision["status"] == "rejected"
    assert staged_decision["decision_reason"] == "确认该提及不纳入本次知识库"
    governance_response = client.get(GOVERNANCE_URL.format(import_job_id), headers=headers(token))
    assert governance_response.status_code == 200, governance_response.text
    governance = governance_response.json()["data"]
    assert not [issue for issue in governance["issues"] if issue["object_type"] == "normalization_decision"]
    assert governance["summary"]["issue_count"] == len(governance["issues"])

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers=headers(token),
    )
    assert publish_response.status_code == 200, publish_response.text
    assert store.normalization_decisions[decision["decision_id"]]["status"] == "rejected"


def test_staged_normalization_review_returns_errors_for_invalid_job_and_decision(client, monkeypatch) -> None:
    token, import_job_id, decision = import_unresolved_guideline(
        client, monkeypatch, "kb-staged-review-errors-001"
    )
    missing_job_response = client.post(
        STAGED_REVIEW_URL.format("00000000-0000-0000-0000-000000000000", decision["decision_id"]),
        headers=headers(token),
        json={"status": "rejected", "reason": "不存在的任务"},
    )
    assert missing_job_response.status_code == 404, missing_job_response.text
    assert missing_job_response.json()["error"]["code"] == "not_found"

    missing_decision_response = client.post(
        STAGED_REVIEW_URL.format(import_job_id, "missing-decision"),
        headers=headers(token),
        json={"status": "rejected", "reason": "不存在的决策"},
    )
    assert missing_decision_response.status_code == 404, missing_decision_response.text
    assert missing_decision_response.json()["error"]["code"] == "not_found"

    missing_concept_response = client.post(
        STAGED_REVIEW_URL.format(import_job_id, decision["decision_id"]),
        headers=headers(token),
        json={
            "status": "resolved",
            "resolved_concept_id": "missing-concept",
            "reason": "无效概念",
        },
    )
    assert missing_concept_response.status_code == 404, missing_concept_response.text
    assert missing_concept_response.json()["error"]["code"] == "not_found"
