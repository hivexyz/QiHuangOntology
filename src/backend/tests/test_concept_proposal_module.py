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


def _import_unresolved_guideline(client, monkeypatch, version_code: str) -> tuple[str, str, dict, list[str]]:
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
            "guide_title": "概念提案测试",
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
    evidence_ids = list(job["staged_snapshot"]["evidence_sources"])
    assert evidence_ids
    return token, import_job_id, decision, evidence_ids


def _create_proposal(client, token: str, import_job_id: str, decision: dict, evidence_ids: list[str]):
    return client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/normalizations/{decision['decision_id']}/concept-proposals",
        headers=_headers(token),
        json={
            "concept_type": "Pattern",
            "standard_name": "月光虚证",
            "definition": "由月光相关因素引起的待确认证候定义。",
            "evidence_ids": [evidence_ids[0]],
            "source_note": "来自指南中的未归一化提及",
            "operator_id": "curator_proposer",
        },
    )


def test_create_and_list_concept_proposal_include_evidence_context(client, monkeypatch) -> None:
    token, import_job_id, decision, evidence_ids = _import_unresolved_guideline(
        client, monkeypatch, "kb-concept-proposal-create-001"
    )

    response = _create_proposal(client, token, import_job_id, decision, evidence_ids)
    assert response.status_code == 200, response.text
    proposal = response.json()["data"]
    assert proposal["status"] == "pending_review"
    assert proposal["decision_id"] == decision["decision_id"]
    assert proposal["mention_id"] == decision["mention_id"]
    assert proposal["evidence_ids"] == [evidence_ids[0]]
    assert proposal["evidence_sources"] == [
        {
            "evidence_id": evidence_ids[0],
            "source_title": "概念提案测试",
            "source_text": proposal["evidence_sources"][0]["source_text"],
            "source_uri": "概念提案测试",
        }
    ]

    duplicate_response = _create_proposal(client, token, import_job_id, decision, evidence_ids)
    assert duplicate_response.status_code == 409, duplicate_response.text
    assert duplicate_response.json()["error"]["code"] == "invalid_state"

    list_response = client.get(
        f"/api/v1/ontology/import-jobs/{import_job_id}/concept-proposals",
        headers=_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["data"] == [proposal]

    governance_response = client.get(
        f"/api/v1/ontology/import-jobs/{import_job_id}/governance",
        headers=_headers(token),
    )
    assert governance_response.status_code == 200, governance_response.text
    governance = governance_response.json()["data"]
    assert governance["concept_proposals"] == [proposal]
    normalization_issue = next(
        issue for issue in governance["issues"] if issue["object_type"] == "normalization_decision"
    )
    assert normalization_issue["evidence_ids"] == sorted(evidence_ids)
    assert {item["evidence_id"] for item in normalization_issue["evidence_sources"]} == set(evidence_ids)


def test_create_concept_proposal_rejects_invalid_evidence_and_type(client, monkeypatch) -> None:
    token, import_job_id, decision, evidence_ids = _import_unresolved_guideline(
        client, monkeypatch, "kb-concept-proposal-invalid-001"
    )

    invalid_evidence = _create_proposal(client, token, import_job_id, decision, ["missing-evidence"])
    assert invalid_evidence.status_code == 400, invalid_evidence.text
    assert invalid_evidence.json()["error"]["code"] == "invalid_request"

    invalid_type = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/normalizations/{decision['decision_id']}/concept-proposals",
        headers=_headers(token),
        json={
            "concept_type": "NotAnOntologyType",
            "standard_name": "月光虚证",
            "definition": "待确认定义",
            "evidence_ids": [evidence_ids[0]],
            "operator_id": "curator_proposer",
        },
    )
    assert invalid_type.status_code == 400, invalid_type.text
    assert invalid_type.json()["error"]["code"] == "invalid_request"
    assert store.import_jobs[UUID(import_job_id)]["staged_snapshot"].get("concept_proposals", {}) == {}


def test_approve_concept_proposal_stages_and_publishes_concept(client, monkeypatch) -> None:
    token, import_job_id, decision, evidence_ids = _import_unresolved_guideline(
        client, monkeypatch, "kb-concept-proposal-approve-001"
    )
    proposal_response = _create_proposal(client, token, import_job_id, decision, evidence_ids)
    assert proposal_response.status_code == 200, proposal_response.text
    proposal_id = proposal_response.json()["data"]["proposal_id"]

    review_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/concept-proposals/{proposal_id}/review",
        headers=_headers(token),
        json={"status": "approved", "reason": "证据足以支持新增概念", "operator_id": "curator_reviewer"},
    )
    assert review_response.status_code == 200, review_response.text
    reviewed = review_response.json()["data"]
    concept_id = reviewed["proposed_concept_id"]
    assert reviewed["status"] == "approved"
    assert concept_id

    job = store.import_jobs[UUID(import_job_id)]
    staged_snapshot = job["staged_snapshot"]
    staged_concept = staged_snapshot["ontology_entities"][concept_id]
    assert staged_concept["label"] == "Pattern"
    assert staged_concept["standard_name"] == "月光虚证"
    assert staged_concept["aliases"] == ["月光虚证"]
    assert staged_concept["attributes"]["definition"] == "由月光相关因素引起的待确认证候定义。"
    assert staged_concept["attributes"]["proposal_id"] == proposal_id
    assert staged_concept["attributes"]["evidence_ids"] == [evidence_ids[0]]
    staged_decision = staged_snapshot["normalization_decisions"][decision["decision_id"]]
    assert staged_decision["status"] == "resolved"
    assert staged_decision["resolved_concept_id"] == concept_id
    assert staged_decision["canonical_name"] == "月光虚证"
    assert staged_decision["confidence_score"] == 1.0
    assert staged_decision["candidate_list"][0]["concept_id"] == concept_id
    assert any(
        change["object_id"] == proposal_id and change["to_version"] == "approved"
        for change in staged_snapshot["change_records"].values()
    )
    assert concept_id not in store.ontology_entities

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers=_headers(token),
    )
    assert publish_response.status_code == 200, publish_response.text
    assert store.ontology_entities[concept_id] == staged_concept
    assert store.normalization_decisions[decision["decision_id"]]["resolved_concept_id"] == concept_id
    assert any(
        alias["concept_entity_id"] == concept_id and alias["alias_text"] == "月光虚证"
        for alias in store.concept_aliases.values()
    )
    assert proposal_id in store.import_jobs[UUID(import_job_id)]["staged_snapshot"]["concept_proposals"]


def test_reject_concept_proposal_does_not_create_concept(client, monkeypatch) -> None:
    token, import_job_id, decision, evidence_ids = _import_unresolved_guideline(
        client, monkeypatch, "kb-concept-proposal-reject-001"
    )
    proposal_response = _create_proposal(client, token, import_job_id, decision, evidence_ids)
    proposal_id = proposal_response.json()["data"]["proposal_id"]

    review_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/concept-proposals/{proposal_id}/review",
        headers=_headers(token),
        json={"status": "rejected", "reason": "证据不足以建立正式概念", "operator_id": "curator_reviewer"},
    )
    assert review_response.status_code == 200, review_response.text
    rejected = review_response.json()["data"]
    assert rejected["status"] == "rejected"
    assert rejected["proposed_concept_id"] is None
    assert rejected["review_reason"] == "证据不足以建立正式概念"

    staged_snapshot = store.import_jobs[UUID(import_job_id)]["staged_snapshot"]
    assert not [
        concept
        for concept in staged_snapshot["ontology_entities"].values()
        if concept.get("attributes", {}).get("proposal_id") == proposal_id
    ]
    assert staged_snapshot["normalization_decisions"][decision["decision_id"]]["status"] == "unresolved"


def test_review_missing_concept_proposal_returns_not_found(client, monkeypatch) -> None:
    token, import_job_id, _, _ = _import_unresolved_guideline(
        client, monkeypatch, "kb-concept-proposal-missing-001"
    )
    response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/concept-proposals/missing-proposal/review",
        headers=_headers(token),
        json={"status": "approved", "reason": "不存在的提案", "operator_id": "curator_reviewer"},
    )
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
