from __future__ import annotations

import base64
import json
from uuid import uuid4

from qihuang_shield.services.guideline_llm import GUIDELINE_LLM_PROMPT_VERSION
from qihuang_shield.dependencies import ontology_service, store
import qihuang_shield.services.guideline_import as guideline_import_module
from qihuang_shield.services.guideline_import import GuidelineOntologyExtractor
from qihuang_shield.services.ontology_base import OntologyBaseService
from qihuang_shield.services.ontology_base_validator import OntologyBaseValidator
from qihuang_shield.services.ontology_query import OntologyQueryService
from qihuang_shield.services.relation_schema import canonical_relation_code
from qihuang_shield.utils import utcnow


GUIDELINE_IMPORT_URL = "/api/v1/ontology/guideline-imports"


def login_admin_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def test_guideline_import_returns_ai_telemetry_and_extraction_stats(client) -> None:
    token = login_admin_token(client)

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-demo.md",
            "source_type": "txt",
            "target_version_code": "kb-test-ai-001",
            "guide_title": "测试指南",
            "guide_text": "附子：功效：回阳救逆。禁用于孕妇及代茶饮场景，不宜与海藻同服。",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    summary = payload["summary"]
    telemetry = summary["ai_telemetry"]
    stats = summary["extraction_stats"]

    assert summary["extractor_engine"] in {"rule", "rule_fallback", "llm"}
    assert telemetry["phase"] == "extracted"
    assert telemetry["extractor_engine"] == summary["extractor_engine"]
    assert "entity_count" in telemetry
    assert stats["material_count"] >= 1
    assert stats["input_char_count"] > 0
    assert stats["input_sha256"]


def test_guideline_import_llm_fallback_sets_reason_and_prompt_metadata(client, monkeypatch) -> None:
    token = login_admin_token(client)
    from qihuang_shield.dependencies import ontology_service

    monkeypatch.setattr(ontology_service.guideline_llm_extractor, "is_enabled", lambda: True)

    def _boom(*args, **kwargs):
        raise RuntimeError("mock llm down")

    monkeypatch.setattr(ontology_service.guideline_llm_extractor, "extract", _boom)

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-fallback.md",
            "source_type": "txt",
            "target_version_code": "kb-test-ai-002",
            "guide_title": "回退测试",
            "guide_text": "甘草：适用于食疗场景，但与海藻配伍禁忌。",
        },
    )

    assert response.status_code == 200, response.text
    summary = response.json()["data"]["summary"]
    assert summary["fallback_used"] is True
    assert "回退规则抽取" in summary["fallback_reason"]
    assert summary["extractor_engine"] == "rule_fallback"
    assert summary["ai_telemetry"]["fallback_used"] is True


def test_guideline_llm_prompt_version_constant_exposed() -> None:
    assert GUIDELINE_LLM_PROMPT_VERSION == "ontology-candidate-extract-v2"


def test_guideline_import_stages_assertions_and_evidence_until_publish(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-stage.md",
            "source_type": "txt",
            "target_version_code": "kb-stage-001",
            "guide_title": "分阶段发布测试",
            "guide_text": "附子：禁用于孕妇及代茶饮场景，不宜与海藻同服。",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == payload["import_job"]["import_job_id"]
    )
    assert payload["summary"]["assertion_count"] >= 2
    assert payload["summary"]["evidence_count"] >= 1
    assert payload["summary"]["alias_count"] >= 2
    job = store.import_jobs[import_job_id]
    staged_mentions = job["staged_snapshot"].get("mentions") or {}
    staged_decisions = job["staged_snapshot"].get("normalization_decisions") or {}
    assert "knowledge_cards" not in job["staged_snapshot"]
    assert staged_mentions
    assert staged_decisions
    assert any(mention["surface_text"] == "附子" for mention in staged_mentions.values())
    assert any(decision["canonical_name"] == "附子" for decision in staged_decisions.values())
    assert any(version["version_code"] == "kb-stage-001" and version["status"] == "draft" for version in store.kb_versions.values())

    query = OntologyQueryService(store)
    pre_publish = query.query_entity_constraints(["mat_001"])
    assert "pregnant" in pre_publish.not_for_populations.get("mat_001", [])
    assert all(assertion["kb_version"] != "kb-stage-001" for assertion in store.ontology_assertions.values())

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text
    assert any(assertion["kb_version"] == "kb-stage-001" for assertion in store.ontology_assertions.values())
    assert any(evidence["kb_version"] == "kb-stage-001" for evidence in store.evidence_sources.values())
    assert any(alias["kb_version"] == "kb-stage-001" for alias in store.concept_aliases.values())
    assert any(document["kb_version"] == "kb-stage-001" for document in store.guideline_documents.values())
    assert any(mention["kb_version"] == "kb-stage-001" for mention in store.mentions.values())
    assert any(decision["kb_version"] == "kb-stage-001" for decision in store.normalization_decisions.values())
    published_assertion = next(assertion for assertion in store.ontology_assertions.values() if assertion["kb_version"] == "kb-stage-001")
    published_evidence = next(evidence for evidence in store.evidence_sources.values() if evidence["kb_version"] == "kb-stage-001")
    published_decision = next(decision for decision in store.normalization_decisions.values() if decision["kb_version"] == "kb-stage-001")
    document_id = published_assertion.get("document_id")
    assert document_id
    assert published_evidence.get("document_id") == document_id
    assert store.guideline_documents[document_id]["status"] == "published"
    decision_response = client.get(
        f"/api/v1/ontology/normalizations/{published_decision['decision_id']}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert decision_response.status_code == 200, decision_response.text
    assert decision_response.json()["data"]["canonical_name"] == published_decision["canonical_name"]
    assert any(
        projection.get("kb_version") == "kb-stage-001"
        and projection.get("projection_type") == "knowledge_card"
        and projection.get("derived_from_assertions") is True
        for projection in store.knowledge_card_projections.values()
    )
    assert any(
        card.get("kb_version") == "kb-stage-001"
        and card.get("derived_from_assertions") is True
        for card in store.knowledge_cards.values()
    )


def test_guideline_import_records_unresolved_normalization_decisions(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-unresolved.md",
            "source_type": "txt",
            "target_version_code": "kb-unresolved-001",
            "guide_title": "未归一术语测试",
            "guide_text": "附子：证候：月光虚证；禁用于孕妇。",
        },
    )

    assert response.status_code == 200, response.text
    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == response.json()["data"]["import_job"]["import_job_id"]
    )
    staged_decisions = store.import_jobs[import_job_id]["staged_snapshot"]["normalization_decisions"]
    staged_mentions = store.import_jobs[import_job_id]["staged_snapshot"]["mentions"]
    unresolved = [
        decision for decision in staged_decisions.values()
        if decision["status"] == "unresolved"
    ]
    assert unresolved
    unresolved_mention = staged_mentions[unresolved[0]["mention_id"]]
    assert unresolved_mention["surface_text"] == "月光虚证"
    assert unresolved[0]["resolved_concept_id"] is None
    assert unresolved[0]["candidate_list"] == []

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text
    assert any(
        decision["kb_version"] == "kb-unresolved-001"
        and decision["status"] == "unresolved"
        for decision in store.normalization_decisions.values()
    )


def test_guideline_import_records_ambiguous_normalization_decisions(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-ambiguous.md",
            "source_type": "txt",
            "target_version_code": "kb-ambiguous-001",
            "guide_title": "歧义归一测试",
            "guide_text": "附子：证候：阳虚；体质：阳虚体质；禁用于孕妇。",
        },
    )

    assert response.status_code == 200, response.text
    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == response.json()["data"]["import_job"]["import_job_id"]
    )
    staged_decisions = store.import_jobs[import_job_id]["staged_snapshot"]["normalization_decisions"]
    staged_mentions = store.import_jobs[import_job_id]["staged_snapshot"]["mentions"]
    ambiguous = [
        decision for decision in staged_decisions.values()
        if decision["status"] == "ambiguous"
    ]

    assert ambiguous
    ambiguous_mention = staged_mentions[ambiguous[0]["mention_id"]]
    assert ambiguous_mention["surface_text"] == "阳虚"
    assert ambiguous[0]["resolved_concept_id"] is None
    candidate_types = {candidate["concept_type"] for candidate in ambiguous[0]["candidate_list"]}
    assert {"Pattern", "Constitution"}.issubset(candidate_types)


def test_review_normalization_decision_can_reject_ambiguous_decision(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-review-reject.md",
            "source_type": "txt",
            "target_version_code": "kb-review-reject-001",
            "guide_title": "归一拒绝测试",
            "guide_text": "附子：证候：阳虚；体质：阳虚体质；禁用于孕妇。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == response.json()["data"]["import_job"]["import_job_id"]
    )
    ambiguous_decision = next(
        decision for decision in store.import_jobs[import_job_id]["staged_snapshot"]["normalization_decisions"].values()
        if decision["status"] == "ambiguous"
    )
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    review_response = client.post(
        f"/api/v1/ontology/normalizations/{ambiguous_decision['decision_id']}/review",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "status": "rejected",
            "reason": "人工确认该提及不应入库",
            "operator_id": "curator_001",
        },
    )

    assert review_response.status_code == 200, review_response.text
    data = review_response.json()["data"]
    assert data["status"] == "rejected"
    assert data["resolved_concept_id"] is None
    assert any(
        change["object_id"] == ambiguous_decision["decision_id"]
        and change["object_type"] == "normalization_decision"
        and change["to_version"] == "rejected"
        for change in store.change_records.values()
    )


def test_review_normalization_decision_can_resolve_unresolved_decision(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-review-resolve.md",
            "source_type": "txt",
            "target_version_code": "kb-review-resolve-001",
            "guide_title": "归一解决测试",
            "guide_text": "附子：证候：月光虚证；禁用于孕妇。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == response.json()["data"]["import_job"]["import_job_id"]
    )
    unresolved_decision = next(
        decision for decision in store.import_jobs[import_job_id]["staged_snapshot"]["normalization_decisions"].values()
        if decision["status"] == "unresolved"
    )
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    review_response = client.post(
        f"/api/v1/ontology/normalizations/{unresolved_decision['decision_id']}/review",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "status": "resolved",
            "resolved_concept_id": "mat_001",
            "create_alias": True,
            "reason": "人工归一到附子",
            "operator_id": "curator_001",
        },
    )

    assert review_response.status_code == 200, review_response.text
    data = review_response.json()["data"]
    assert data["status"] == "resolved"
    assert data["resolved_concept_id"] == "mat_001"
    assert data["canonical_name"] == "附子"
    created_alias = next(
        alias for alias in store.concept_aliases.values()
        if alias.get("alias_text") == "月光虚证"
        and alias.get("concept_entity_id") == "mat_001"
        and alias.get("alias_type") == "reviewed_normalization_alias"
    )
    assert created_alias["status"] == "draft"
    assert any(
        change["object_id"] == unresolved_decision["decision_id"]
        and change["to_version"] == "resolved"
        and change["impact_note"] == f"created_alias_id={created_alias['alias_id']}"
        for change in store.change_records.values()
    )

    alias_response = client.post(
        f"/api/v1/ontology/concept-aliases/{created_alias['alias_id']}/review",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "status": "published",
            "reason": "确认作为附子别名发布",
            "operator_id": "curator_001",
        },
    )
    assert alias_response.status_code == 200, alias_response.text
    assert alias_response.json()["data"]["status"] == "published"
    assert "月光虚证" in store.ontology_entities["mat_001"]["aliases"]
    assert any(
        change["object_id"] == created_alias["alias_id"]
        and change["object_type"] == "concept_alias"
        and change["to_version"] == "published"
        for change in store.change_records.values()
    )


def test_review_concept_alias_can_reject_draft_alias(client) -> None:
    token = login_admin_token(client)
    store.concept_aliases["alias_review_reject_001"] = {
        "alias_id": "alias_review_reject_001",
        "alias_text": "拒绝别名",
        "concept_entity_id": "mat_001",
        "canonical_name": "附子",
        "kb_version": "kb-2026-05-29-01",
        "status": "draft",
        "alias_type": "reviewed_normalization_alias",
    }

    response = client.post(
        "/api/v1/ontology/concept-aliases/alias_review_reject_001/review",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "status": "rejected",
            "reason": "不是有效别名",
            "operator_id": "curator_001",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "rejected"
    assert "拒绝别名" not in store.ontology_entities["mat_001"]["aliases"]


def test_publish_terminology_version_publishes_alias_batch(client) -> None:
    token = login_admin_token(client)
    store.concept_aliases["alias_term_publish_001"] = {
        "alias_id": "alias_term_publish_001",
        "alias_text": "术语批次别名",
        "concept_entity_id": "mat_001",
        "canonical_name": "附子",
        "kb_version": "terminology-draft",
        "status": "draft",
        "alias_type": "reviewed_normalization_alias",
    }

    response = client.post(
        "/api/v1/ontology/terminology/versions/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "version_id": "terminology-resource-test-001",
            "version_name": "术语资源测试版本",
            "alias_ids": ["alias_term_publish_001"],
            "change_summary": "发布术语别名测试批次",
            "operator_id": "curator_001",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["version_id"] == "terminology-resource-test-001"
    assert data["version_type"] == "terminology_resource"
    assert store.concept_aliases["alias_term_publish_001"]["status"] == "published"
    assert store.concept_aliases["alias_term_publish_001"]["kb_version"] == "terminology-resource-test-001"
    assert "术语批次别名" in store.ontology_entities["mat_001"]["aliases"]
    assert any(
        change["object_id"] == "alias_term_publish_001"
        and change["change_type"] == "publish"
        and change["to_version"] == "terminology-resource-test-001"
        for change in store.change_records.values()
    )
    rollback_response = client.post(
        "/api/v1/ontology/terminology/versions/terminology-resource-test-001/rollback",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        params={"operator_id": "curator_001"},
    )
    assert rollback_response.status_code == 200, rollback_response.text
    assert rollback_response.json()["data"]["status"] == "rolled_back"
    assert store.concept_aliases["alias_term_publish_001"]["status"] == "draft"
    assert "术语批次别名" not in store.ontology_entities["mat_001"]["aliases"]
    assert any(
        change["object_id"] == "alias_term_publish_001"
        and change["change_type"] == "rollback"
        and change["from_version"] == "terminology-resource-test-001"
        for change in store.change_records.values()
    )


def test_list_normalization_decisions_filters_governance_queue(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-queue.md",
            "source_type": "txt",
            "target_version_code": "kb-queue-001",
            "guide_title": "归一队列测试",
            "guide_text": "附子：证候：阳虚、月光虚证；体质：阳虚体质；禁用于孕妇。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == response.json()["data"]["import_job"]["import_job_id"]
    )
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    ambiguous_response = client.get(
        "/api/v1/ontology/normalizations",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        params={
            "status": "ambiguous",
            "kb_version": "kb-queue-001",
            "source_type": "guideline_import",
        },
    )
    unresolved_response = client.get(
        "/api/v1/ontology/normalizations",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        params={
            "status": "unresolved",
            "kb_version": "kb-queue-001",
            "source_type": "guideline_import",
        },
    )

    assert ambiguous_response.status_code == 200, ambiguous_response.text
    assert unresolved_response.status_code == 200, unresolved_response.text
    ambiguous_items = ambiguous_response.json()["data"]
    unresolved_items = unresolved_response.json()["data"]
    assert any(item["status"] == "ambiguous" for item in ambiguous_items)
    assert any(item["status"] == "unresolved" for item in unresolved_items)
    assert all(item["kb_version"] == "kb-queue-001" for item in ambiguous_items + unresolved_items)


def test_batch_review_normalization_decisions_rejects_queue_items(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-batch-review.md",
            "source_type": "txt",
            "target_version_code": "kb-batch-review-001",
            "guide_title": "批量归一治理测试",
            "guide_text": "附子：证候：月光虚证、星火虚证；禁用于孕妇。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == response.json()["data"]["import_job"]["import_job_id"]
    )
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text
    decision_ids = [
        decision["decision_id"]
        for decision in store.normalization_decisions.values()
        if decision["kb_version"] == "kb-batch-review-001" and decision["status"] == "unresolved"
    ]
    assert len(decision_ids) >= 2

    batch_response = client.post(
        "/api/v1/ontology/normalizations/batch-review",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "decision_ids": decision_ids[:2],
            "status": "rejected",
            "reason": "批量确认不入库",
            "operator_id": "curator_001",
        },
    )

    assert batch_response.status_code == 200, batch_response.text
    reviewed = batch_response.json()["data"]
    assert [item["status"] for item in reviewed] == ["rejected", "rejected"]
    assert all(store.normalization_decisions[item["decision_id"]]["status"] == "rejected" for item in reviewed)
    changed_ids = {
        change["object_id"]
        for change in store.change_records.values()
        if change["object_type"] == "normalization_decision"
        and change["to_version"] == "rejected"
    }
    assert set(decision_ids[:2]).issubset(changed_ids)


def test_publish_import_job_rejects_invalid_staged_assertion(client) -> None:
    token = login_admin_token(client)
    kb_version_id = uuid4()
    import_job_id = uuid4()
    now = utcnow()
    store.kb_versions[kb_version_id] = {
        "kb_version_id": kb_version_id,
        "version_code": "kb-invalid-publish-001",
        "status": "draft",
        "source_type": "test",
        "source_checksum": None,
        "validation_report": {"warnings": 0, "errors": 0},
        "snapshot_uri": None,
        "published_by": None,
        "published_at": None,
        "rollback_from_version_id": None,
        "created_at": now,
        "updated_at": now,
    }
    store.import_jobs[import_job_id] = {
        "import_job_id": import_job_id,
        "kb_version_id": kb_version_id,
        "status": "extracted",
        "source_uri": "invalid-staged.md",
        "source_type": "test",
        "warning_count": 0,
        "error_count": 0,
        "validation_report": {"message": "manual invalid staged snapshot"},
        "created_at": now,
        "finished_at": now,
        "staged_snapshot": {
            "ontology_entities": {
                "pop_invalid_publish_001": {
                    "entity_id": "pop_invalid_publish_001",
                    "label": "Population",
                    "standard_name": "孕妇",
                    "aliases": [],
                    "kb_version": "kb-invalid-publish-001",
                    "attributes": {},
                },
                "eff_invalid_publish_001": {
                    "entity_id": "eff_invalid_publish_001",
                    "label": "Effect",
                    "standard_name": "温阳",
                    "aliases": [],
                    "kb_version": "kb-invalid-publish-001",
                    "attributes": {},
                },
            },
            "knowledge_cards": {},
            "ontology_assertions": {
                "assert_invalid_publish_domain": {
                    "assertion_id": "assert_invalid_publish_domain",
                    "subject_entity_id": "pop_invalid_publish_001",
                    "predicate_type": "HAS_EFFECT",
                    "object_entity_id": "eff_invalid_publish_001",
                    "object_value": "温阳",
                    "kb_version": "kb-invalid-publish-001",
                    "status": "draft",
                    "evidence_ids": [],
                    "document_id": None,
                }
            },
            "evidence_sources": {},
            "concept_aliases": {},
            "guideline_documents": {},
        },
    }

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )

    assert publish_response.status_code == 409, publish_response.text
    assert publish_response.json()["error"]["code"] == "ontology_publish_validation_failed"
    assert "assert_invalid_publish_domain" not in store.ontology_assertions
    assert store.kb_versions[kb_version_id]["status"] == "draft"
    assert store.import_jobs[import_job_id]["status"] == "extracted"


def test_knowledge_card_can_be_derived_from_published_assertions(client) -> None:
    query = OntologyQueryService(store)
    constraints = query.query_entity_constraints(["mat_001", "mat_003"])

    assert "pregnant" in constraints.not_for_populations["mat_001"]
    assert "tea_drink" in constraints.prohibited_contexts["mat_001"]
    assert any(
        pair["entity_a"] == "mat_001" and pair["entity_b"] == "mat_003"
        for pair in constraints.contraindication_pairs
    )

    card = ontology_service.get_knowledge_card("mat_001")
    assert card.derived_from_assertions is True
    assert card.assertion_count >= 1
    assert card.evidence_count >= 1


def test_knowledge_card_projection_rebuilds_without_legacy_card() -> None:
    store.knowledge_cards.pop("mat_001", None)
    store.knowledge_card_projections.pop("mat_001", None)

    card = ontology_service.get_knowledge_card("mat_001")

    assert card.derived_from_assertions is True
    assert "pregnant" in card.not_for_populations
    assert "tea_drink" in card.prohibited_contexts
    assert card.assertion_count >= 1
    assert "mat_001" in store.knowledge_card_projections
    assert store.knowledge_card_projections["mat_001"]["derived_from_assertions"] is True


def test_query_constraints_do_not_fallback_to_legacy_knowledge_cards() -> None:
    query = OntologyQueryService(store)
    original_assertions = dict(store.ontology_assertions)
    original_projections = dict(store.knowledge_card_projections)
    original_legacy_cards = dict(store.knowledge_cards)
    try:
        store.ontology_assertions = {}
        store.knowledge_card_projections = {}
        store.knowledge_cards["mat_001"] = {
            "entity": {
                "entity_id": "mat_001",
                "standard_name": "附子",
                "label": "Material",
                "risk_level": "high",
            },
            "kb_version": "kb-2026-05-29-01",
            "prohibited_contexts": ["legacy_only_context"],
            "not_for_populations": ["legacy_only_population"],
            "contraindications": [
                {
                    "target_entity_id": "mat_003",
                    "target_name": "海藻",
                    "relation": "CONTRAINDICATED_WITH",
                }
            ],
        }

        constraints = query.query_entity_constraints(["mat_001", "mat_003"])

        assert constraints.prohibited_contexts == {}
        assert constraints.not_for_populations == {}
        assert constraints.contraindication_pairs == []
    finally:
        store.ontology_assertions = original_assertions
        store.knowledge_card_projections = original_projections
        store.knowledge_cards = original_legacy_cards


def test_list_assertions_filters_by_condition_context() -> None:
    service = OntologyBaseService(store)

    matching = service.list_assertions(
        predicate_type="HAS_PATHOGENESIS",
        subject_entity_id="syn_001",
        condition_context={"pathogenesis": "脾失健运"},
    )
    missing_required = service.list_assertions(
        predicate_type="HAS_PATHOGENESIS",
        subject_entity_id="syn_001",
        condition_context={"pathogenesis": "痰湿内阻"},
    )
    excluded = service.list_assertions(
        predicate_type="HAS_PATHOGENESIS",
        subject_entity_id="syn_001",
        condition_context={"pathogenesis": "脾失健运", "pattern": "热证"},
    )

    assert [item.assertion_id for item in matching] == ["assert_base_pattern_path"]
    assert missing_required == []
    assert excluded == []


def test_list_assertions_condition_context_matches_normalized_concept_id() -> None:
    service = OntologyBaseService(store)

    matching = service.list_assertions(
        predicate_type="HAS_PATHOGENESIS",
        subject_entity_id="syn_001",
        condition_context={"pathogenesis_id": "path_001"},
    )

    assert [item.assertion_id for item in matching] == ["assert_base_pattern_path"]


def test_list_assertions_filters_by_numeric_dose_condition_context() -> None:
    store.condition_sets["cond_dose_over_9"] = {
        "condition_set_id": "cond_dose_over_9",
        "logic": {
            "all": [
                {
                    "type": "dose",
                    "operator": "gte",
                    "value": 9,
                    "value_type": "number",
                }
            ]
        },
        "note": "剂量大于等于 9g 时成立",
    }
    store.ontology_assertions["assert_dose_condition_001"] = {
        "assertion_id": "assert_dose_condition_001",
        "subject_entity_id": "mat_001",
        "predicate_type": "HAS_DOSE",
        "object_entity_id": None,
        "object_value": "9克以上",
        "kb_version": "kb-2026-05-29-01",
        "status": "published",
        "evidence_ids": [],
        "document_id": None,
        "condition_set_id": "cond_dose_over_9",
    }
    service = OntologyBaseService(store)

    matching = service.list_assertions(
        predicate_type="HAS_DOSE",
        subject_entity_id="mat_001",
        condition_context={"dose": 10},
    )
    below_threshold = service.list_assertions(
        predicate_type="HAS_DOSE",
        subject_entity_id="mat_001",
        condition_context={"dose": 6},
    )

    assert [item.assertion_id for item in matching] == ["assert_dose_condition_001"]
    assert below_threshold == []


def test_list_assertions_filters_by_between_dose_condition_context() -> None:
    store.condition_sets["cond_dose_between_3_9"] = {
        "condition_set_id": "cond_dose_between_3_9",
        "logic": {
            "all": [
                {
                    "type": "dose",
                    "operator": "between",
                    "value": [3, 9],
                    "value_type": "number",
                }
            ]
        },
        "note": "剂量 3-9g 时成立",
    }
    store.ontology_assertions["assert_dose_condition_002"] = {
        "assertion_id": "assert_dose_condition_002",
        "subject_entity_id": "mat_001",
        "predicate_type": "HAS_DOSE",
        "object_entity_id": None,
        "object_value": "3-9克",
        "kb_version": "kb-2026-05-29-01",
        "status": "published",
        "evidence_ids": [],
        "document_id": None,
        "condition_set_id": "cond_dose_between_3_9",
    }
    service = OntologyBaseService(store)

    matching = service.list_assertions(
        predicate_type="HAS_DOSE",
        subject_entity_id="mat_001",
        condition_context={"dose": 6},
    )
    outside_range = service.list_assertions(
        predicate_type="HAS_DOSE",
        subject_entity_id="mat_001",
        condition_context={"dose": 12},
    )

    assert [item.assertion_id for item in matching] == ["assert_dose_condition_002"]
    assert outside_range == []


def test_list_assertions_api_filters_by_condition_context_json(client) -> None:
    token = login_admin_token(client)

    response = client.get(
        "/api/v1/ontology-base/assertions",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        params={
            "predicate_type": "HAS_PATHOGENESIS",
            "subject_entity_id": "syn_001",
            "condition_context_json": json.dumps({"pathogenesis": "脾失健运"}, ensure_ascii=False),
        },
    )

    assert response.status_code == 200, response.text
    assertion_ids = [item["assertion_id"] for item in response.json()["data"]]
    assert assertion_ids == ["assert_base_pattern_path"]


def test_list_assertions_api_excludes_not_condition_context_json(client) -> None:
    token = login_admin_token(client)

    response = client.get(
        "/api/v1/ontology-base/assertions",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        params={
            "predicate_type": "HAS_PATHOGENESIS",
            "subject_entity_id": "syn_001",
            "condition_context_json": json.dumps(
                {"pathogenesis": "脾失健运", "pattern": "热证"},
                ensure_ascii=False,
            ),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


def test_list_assertions_api_rejects_invalid_condition_context_json(client) -> None:
    token = login_admin_token(client)

    response = client.get(
        "/api/v1/ontology-base/assertions",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        params={"condition_context_json": "[not-json"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_condition_context"


def test_assertion_domain_range_constraints_are_validated() -> None:
    extractor = GuidelineOntologyExtractor()
    valid_assertions, warnings = extractor._validate_assertions(
        ontology_entities={
            "mat_a": {"entity_id": "mat_a", "label": "Material", "standard_name": "附子"},
            "pop_a": {"entity_id": "pop_a", "label": "Population", "standard_name": "孕妇"},
        },
        ontology_assertions={
            "assert_bad_effect": {
                "assertion_id": "assert_bad_effect",
                "subject_entity_id": "pop_a",
                "predicate_type": "HAS_EFFECT",
                "object_entity_id": "mat_a",
                "object_value": "附子",
            }
        },
    )

    assert not valid_assertions
    assert any("domain" in warning for warning in warnings)
    assert any("range" in warning for warning in warnings)


def test_assertion_constraints_use_versioned_relation_schema_from_store() -> None:
    extractor = GuidelineOntologyExtractor()
    permissive_schema = {
        **store.relation_schemas,
        "HAS_EFFECT": {
            **store.relation_schemas["HAS_EFFECT"],
            "subject_labels": ["Population"],
            "object_labels": ["Material"],
        },
    }
    valid_assertions, warnings = extractor._validate_assertions(
        ontology_entities={
            "mat_a": {"entity_id": "mat_a", "label": "Material", "standard_name": "附子"},
            "pop_a": {"entity_id": "pop_a", "label": "Population", "standard_name": "孕妇"},
        },
        ontology_assertions={
            "assert_custom_effect": {
                "assertion_id": "assert_custom_effect",
                "subject_entity_id": "pop_a",
                "predicate_type": "HAS_EFFECT",
                "object_entity_id": "mat_a",
                "object_value": "附子",
            }
        },
        relation_schemas=permissive_schema,
    )

    assert "assert_custom_effect" in valid_assertions
    assert warnings == []


def test_assertion_constraints_reject_unknown_relation() -> None:
    extractor = GuidelineOntologyExtractor()
    valid_assertions, warnings = extractor._validate_assertions(
        ontology_entities={
            "mat_a": {"entity_id": "mat_a", "label": "Material", "standard_name": "附子"},
            "eff_a": {"entity_id": "eff_a", "label": "Effect", "standard_name": "温阳"},
        },
        ontology_assertions={
            "assert_unknown_relation": {
                "assertion_id": "assert_unknown_relation",
                "subject_entity_id": "mat_a",
                "predicate_type": "UNREGISTERED_RELATION",
                "object_entity_id": "eff_a",
                "object_value": "温阳",
            }
        },
    )

    assert "assert_unknown_relation" not in valid_assertions
    assert any("未注册" in warning for warning in warnings)


def test_ontology_validator_uses_relation_schema_registry_fallback() -> None:
    store.relation_definitions.pop("INDICATED_FOR_PATTERN", None)
    store.ontology_entities["method_validator_001"] = {
        "entity_id": "method_validator_001",
        "label": "TreatmentMethod",
        "standard_name": "益气健脾",
        "aliases": [],
        "kb_version": "knowledge-content-v0.1",
        "attributes": {},
    }
    store.ontology_entities["pattern_validator_001"] = {
        "entity_id": "pattern_validator_001",
        "label": "Pattern",
        "standard_name": "脾虚",
        "aliases": ["脾气虚证"],
        "kb_version": "knowledge-content-v0.1",
        "attributes": {},
    }
    store.ontology_assertions["assert_validator_pattern_ok"] = {
        "assertion_id": "assert_validator_pattern_ok",
        "subject_entity_id": "method_validator_001",
        "predicate_type": "INDICATED_FOR_PATTERN",
        "object_entity_id": "pattern_validator_001",
        "object_value": "脾虚",
        "kb_version": "knowledge-content-v0.1",
        "status": "published",
        "evidence_ids": [],
        "document_id": None,
    }

    report = OntologyBaseValidator(store).validate()

    assert not any(
        issue.object_id == "assert_validator_pattern_ok"
        and issue.code in {"unknown_relation_definition", "domain_mismatch", "range_mismatch"}
        for issue in report.issues
    )


def test_ontology_validator_reports_schema_registry_domain_mismatch() -> None:
    store.relation_definitions.pop("INDICATED_FOR_PATTERN", None)
    store.ontology_entities["population_validator_001"] = {
        "entity_id": "population_validator_001",
        "label": "Population",
        "standard_name": "孕妇",
        "aliases": [],
        "kb_version": "knowledge-content-v0.1",
        "attributes": {},
    }
    store.ontology_entities["pattern_validator_002"] = {
        "entity_id": "pattern_validator_002",
        "label": "Pattern",
        "standard_name": "脾虚",
        "aliases": [],
        "kb_version": "knowledge-content-v0.1",
        "attributes": {},
    }
    store.ontology_assertions["assert_validator_pattern_bad_domain"] = {
        "assertion_id": "assert_validator_pattern_bad_domain",
        "subject_entity_id": "population_validator_001",
        "predicate_type": "INDICATED_FOR_PATTERN",
        "object_entity_id": "pattern_validator_002",
        "object_value": "脾虚",
        "kb_version": "knowledge-content-v0.1",
        "status": "published",
        "evidence_ids": [],
        "document_id": None,
    }

    report = OntologyBaseValidator(store).validate()

    assert any(
        issue.object_id == "assert_validator_pattern_bad_domain"
        and issue.code == "domain_mismatch"
        for issue in report.issues
    )


def test_guideline_import_distinguishes_herb_and_formula_labels(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-formula.md",
            "source_type": "txt",
            "target_version_code": "kb-formula-001",
            "guide_title": "方剂分类测试",
            "guide_text": "四君子汤：适用于食疗场景。\n附子：禁用于孕妇。",
        },
    )

    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    formula_entity = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-formula-001" and entity["standard_name"] == "四君子汤"
    )
    herb_entity = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-formula-001" and entity["standard_name"] == "附子"
    )
    assert formula_entity["label"] == "Formula"
    assert herb_entity["label"] == "Herb"


def test_guideline_import_builds_stage_entities_and_assertions(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-stage-field.md",
            "source_type": "txt",
            "target_version_code": "kb-stage-field-001",
            "guide_title": "阶段关系测试",
            "guide_text": "黄芪：阶段：恢复期；剂量：3-9克。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    stage = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-stage-field-001"
        and entity["label"] == "Stage"
        and entity["standard_name"] == "恢复期"
    )
    assert stage["attributes"]["stage_type"] == "恢复期"
    assert any(
        assertion["predicate_type"] == "SUITABLE_FOR_STAGE"
        and assertion["object_entity_id"] == stage["entity_id"]
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-stage-field-001"
    )


def test_guideline_import_builds_five_element_generate_restrict_relations(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-five-elements.md",
            "source_type": "txt",
            "target_version_code": "kb-five-elements-001",
            "guide_title": "五行关系测试",
            "guide_text": "柴胡：性味：木；归经：肝经。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    five_elements = {
        entity["attributes"]["property_type"]: entity
        for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-five-elements-001"
        and entity["label"] == "Property"
        and entity["attributes"].get("property_category") == "five_element"
    }
    assertions = [
        assertion for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-five-elements-001"
    ]
    generate_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in assertions
        if assertion["predicate_type"] == "GENERATES"
    }
    restrict_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in assertions
        if assertion["predicate_type"] == "RESTRICTS"
    }
    overact_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in assertions
        if assertion["predicate_type"] == "OVERACTS"
    }
    insult_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in assertions
        if assertion["predicate_type"] == "INSULTS"
    }

    assert set(five_elements) == {"wood", "fire", "earth", "metal", "water"}
    assert (five_elements["wood"]["entity_id"], five_elements["fire"]["entity_id"]) in generate_pairs
    assert (five_elements["wood"]["entity_id"], five_elements["earth"]["entity_id"]) in restrict_pairs
    assert (five_elements["wood"]["entity_id"], five_elements["earth"]["entity_id"]) in overact_pairs
    assert (five_elements["earth"]["entity_id"], five_elements["wood"]["entity_id"]) in insult_pairs


def test_guideline_import_links_meridian_to_organ_property(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-meridian-organ.md",
            "source_type": "txt",
            "target_version_code": "kb-meridian-organ-001",
            "guide_title": "归经脏腑关系测试",
            "guide_text": "柴胡：归经：肝经。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    meridian = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-meridian-organ-001"
        and entity["label"] == "Meridian"
        and entity["standard_name"] == "肝经"
    )
    organ = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-meridian-organ-001"
        and entity["label"] == "Property"
        and entity["attributes"].get("property_category") == "organ"
        and entity["standard_name"] == "肝"
    )
    assert any(
        assertion["predicate_type"] == "ASSOCIATED_WITH_ORGAN"
        and assertion["subject_entity_id"] == meridian["entity_id"]
        and assertion["object_entity_id"] == organ["entity_id"]
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-meridian-organ-001"
    )


def test_guideline_import_covers_twelve_meridian_organ_mappings(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-12-meridians.md",
            "source_type": "txt",
            "target_version_code": "kb-12-meridians-001",
            "guide_title": "十二经脉关系测试",
            "guide_text": "测试药：归经：肺经、大肠经、胃经、脾经、心经、小肠经、膀胱经、肾经、心包经、三焦经、胆经、肝经。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    meridians = {
        entity["standard_name"]: entity
        for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-12-meridians-001"
        and entity["label"] == "Meridian"
    }
    organs = {
        entity["standard_name"]: entity
        for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-12-meridians-001"
        and entity["label"] == "Property"
        and entity["attributes"].get("property_category") == "organ"
    }
    zangfu = {
        entity["standard_name"]: entity
        for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-12-meridians-001"
        and entity["label"] == "ZangFu"
    }
    meridian_systems = {
        entity["standard_name"]: entity
        for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-12-meridians-001"
        and entity["label"] == "MeridianSystem"
    }
    organ_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-12-meridians-001"
        and assertion["predicate_type"] == "ASSOCIATED_WITH_ORGAN"
    }
    zangfu_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-12-meridians-001"
        and assertion["predicate_type"] == "ASSOCIATED_WITH_ZANGFU"
    }
    meridian_system_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-12-meridians-001"
        and assertion["predicate_type"] == "BELONGS_TO_MERIDIAN_SYSTEM"
    }
    flow_pairs = {
        (assertion["subject_entity_id"], assertion["object_entity_id"])
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-12-meridians-001"
        and assertion["predicate_type"] == "FLOWS_TO"
    }

    assert {"肺经", "大肠经", "胃经", "脾经", "心经", "小肠经", "膀胱经", "肾经", "心包经", "三焦经", "胆经", "肝经"}.issubset(meridians)
    assert {"肺", "大肠", "胃", "脾", "心", "小肠", "膀胱", "肾", "心包", "三焦", "胆", "肝"}.issubset(organs)
    assert {"肺", "大肠", "胃", "脾", "心", "小肠", "膀胱", "肾", "心包", "三焦", "胆", "肝"}.issubset(zangfu)
    assert "十二经脉" in meridian_systems
    assert (meridians["大肠经"]["entity_id"], organs["大肠"]["entity_id"]) in organ_pairs
    assert (meridians["三焦经"]["entity_id"], organs["三焦"]["entity_id"]) in organ_pairs
    assert (meridians["大肠经"]["entity_id"], zangfu["大肠"]["entity_id"]) in zangfu_pairs
    assert (meridians["三焦经"]["entity_id"], zangfu["三焦"]["entity_id"]) in zangfu_pairs
    assert (
        meridians["肺经"]["entity_id"],
        meridian_systems["十二经脉"]["entity_id"],
    ) in meridian_system_pairs
    assert (meridians["肺经"]["entity_id"], meridians["大肠经"]["entity_id"]) in flow_pairs
    assert (meridians["肝经"]["entity_id"], meridians["肺经"]["entity_id"]) in flow_pairs


def test_guideline_import_covers_extraordinary_vessels(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-extraordinary-vessels.md",
            "source_type": "txt",
            "target_version_code": "kb-extraordinary-vessels-001",
            "guide_title": "奇经八脉关系测试",
            "guide_text": "测试药：归经：督脉、任脉、冲脉、带脉、阴维脉、阳维脉、阴跷脉、阳跷脉。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    meridians = {
        entity["standard_name"]: entity
        for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-extraordinary-vessels-001"
        and entity["label"] == "Meridian"
    }

    assert {"督脉", "任脉", "冲脉", "带脉", "阴维脉", "阳维脉", "阴跷脉", "阳跷脉"}.issubset(meridians)
    assert all(
        meridian["attributes"]["meridian_system"] == "extraordinary_vessel"
        for meridian in meridians.values()
    )
    meridian_system = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-extraordinary-vessels-001"
        and entity["label"] == "MeridianSystem"
        and entity["standard_name"] == "奇经八脉"
    )
    assert all(
        any(
            assertion["predicate_type"] == "BELONGS_TO_MERIDIAN_SYSTEM"
            and assertion["subject_entity_id"] == meridian["entity_id"]
            and assertion["object_entity_id"] == meridian_system["entity_id"]
            for assertion in store.ontology_assertions.values()
            if assertion["kb_version"] == "kb-extraordinary-vessels-001"
        )
        for meridian in meridians.values()
    )


def test_guideline_import_links_acupoint_to_meridian(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-acupoint.md",
            "source_type": "txt",
            "target_version_code": "kb-acupoint-001",
            "guide_title": "腧穴关系测试",
            "guide_text": "测试药：归经：胃经；腧穴：足三里；定位：外膝眼下三寸；手法：针刺；配穴：内关；症状：腹胀。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    acupoint = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-acupoint-001"
        and entity["label"] == "Acupoint"
        and entity["standard_name"] == "足三里"
    )
    assert acupoint["attributes"]["location_text"] == "外膝眼下三寸"
    assert acupoint["attributes"]["location_reference"] == "外膝眼"
    assert acupoint["attributes"]["location_direction"] == "下"
    assert acupoint["attributes"]["location_distance"] == 3.0
    assert acupoint["attributes"]["location_unit"] == "寸"
    assert acupoint["attributes"]["method_text"] == "针刺"
    meridian = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-acupoint-001"
        and entity["label"] == "Meridian"
        and entity["standard_name"] == "胃经"
    )
    assert any(
        assertion["predicate_type"] == "LOCATED_ON_MERIDIAN"
        and assertion["subject_entity_id"] == acupoint["entity_id"]
        and assertion["object_entity_id"] == meridian["entity_id"]
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-acupoint-001"
    )
    symptom = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-acupoint-001"
        and entity["label"] == "Symptom"
        and entity["standard_name"] == "腹胀"
    )
    assert any(
        assertion["predicate_type"] == "INDICATED_FOR_SYMPTOM"
        and assertion["subject_entity_id"] == acupoint["entity_id"]
        and assertion["object_entity_id"] == symptom["entity_id"]
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-acupoint-001"
    )
    assert any(
        assertion["predicate_type"] == "MANIFESTS_AS_SYMPTOM"
        and assertion["subject_entity_id"] == meridian["entity_id"]
        and assertion["object_entity_id"] == symptom["entity_id"]
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-acupoint-001"
    )
    paired_acupoint = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-acupoint-001"
        and entity["label"] == "Acupoint"
        and entity["standard_name"] == "内关"
    )
    assert any(
        assertion["predicate_type"] == "COMBINES_WITH"
        and assertion["subject_entity_id"] == acupoint["entity_id"]
        and assertion["object_entity_id"] == paired_acupoint["entity_id"]
        for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-acupoint-001"
    )


def test_guideline_import_parses_dose_range_attributes(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "guideline-dose-range.md",
            "source_type": "txt",
            "target_version_code": "kb-dose-range-001",
            "guide_title": "剂量范围测试",
            "guide_text": "柴胡：剂量：3-9克。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text
    dose_entity = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-dose-range-001"
        and entity["label"] == "Dose"
    )
    assert dose_entity["attributes"]["dose_min"] == 3.0
    assert dose_entity["attributes"]["dose_max"] == 9.0
    assert dose_entity["attributes"]["dose_unit"] == "g"


def test_decode_guide_file_supports_pdf(monkeypatch) -> None:
    extractor = GuidelineOntologyExtractor()

    class _FakePage:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class _FakePdfReader:
        def __init__(self, stream) -> None:
            assert stream.read(4) == b"%PDF"
            stream.seek(0)
            self.pages = [
                _FakePage("附子：回阳救逆。"),
                _FakePage("禁用于孕妇。"),
            ]

    monkeypatch.setattr(guideline_import_module, "PdfReader", _FakePdfReader)

    text, warnings = extractor.decode_guide_file(
        "guideline.pdf",
        base64.b64encode(b"%PDF-1.4\nfake pdf bytes").decode("ascii"),
    )

    assert "附子：回阳救逆。" in text
    assert "禁用于孕妇。" in text
    assert warnings == []


def test_owl_import_preserves_semantic_type_and_subclass_assertion(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    owl_content = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:ex="http://example.org/onto#">
  <owl:Class rdf:about="http://example.org/onto#Formula"/>
  <owl:Class rdf:about="http://example.org/onto#SiJunZiTang">
    <rdfs:label>四君子汤</rdfs:label>
    <rdfs:subClassOf rdf:resource="http://example.org/onto#Formula"/>
  </owl:Class>
</rdf:RDF>"""

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "owl-formula.owl",
            "source_type": "owl",
            "target_version_code": "kb-owl-001",
            "guide_title": "OWL 语义类型测试",
            "guide_text": owl_content,
        },
    )

    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    entity = next(
        item for item in store.ontology_entities.values()
        if item["kb_version"] == "kb-owl-001" and item["standard_name"] == "四君子汤"
    )
    assert entity["label"] == "Formula"
    subclass_assertion = next(
        assertion for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-owl-001" and assertion["predicate_type"] == "SUBCLASS_OF"
    )
    assert subclass_assertion["object_value"] == "Formula"

    entity_id = entity["entity_id"]
    detail_response = client.get(
        f"/api/v1/ontology/knowledge-cards/{entity_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()["data"]
    assert any(item["predicate_type"] == "SUBCLASS_OF" for item in detail["assertions"])
    assert detail["guideline_documents"]

    projection_response = client.get(
        f"/api/v1/ontology/projections/{entity_id}",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert projection_response.status_code == 200, projection_response.text
    assert projection_response.json()["data"] == detail

    ancestors = OntologyQueryService(store).query_ancestors([entity_id], kb_version="kb-owl-001")
    assert [item.standard_name for item in ancestors[entity_id]] == ["Formula"]


def test_owl_import_reports_unresolved_class_and_property_mappings(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    owl_content = """<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
         xmlns:owl="http://www.w3.org/2002/07/owl#"
         xmlns:ex="http://example.org/onto#">
  <owl:Class rdf:about="http://example.org/onto#MysteryThing">
    <rdfs:label>玄妙实体</rdfs:label>
  </owl:Class>
  <owl:ObjectProperty rdf:about="http://example.org/onto#hasMysteryLink">
    <rdfs:domain rdf:resource="http://example.org/onto#MysteryThing"/>
    <rdfs:range rdf:resource="http://example.org/onto#MysteryThing"/>
  </owl:ObjectProperty>
</rdf:RDF>"""

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "owl-unresolved.owl",
            "source_type": "owl",
            "target_version_code": "kb-owl-unresolved-001",
            "guide_title": "OWL 未解析映射测试",
            "guide_text": owl_content,
        },
    )

    assert response.status_code == 200, response.text
    summary = response.json()["data"]["summary"]
    warnings = summary["warnings"]
    assert any("Unresolved OWL class mapping: 玄妙实体" in item for item in warnings)
    assert any("Unresolved OWL property mapping: hasmysterylink" in item for item in warnings)

    import_job_id = next(
        job_id for job_id in store.import_jobs
        if str(job_id) == response.json()["data"]["import_job"]["import_job_id"]
    )
    staged_snapshot = store.import_jobs[import_job_id]["staged_snapshot"]
    entity = next(
        item for item in staged_snapshot["ontology_entities"].values()
        if item["standard_name"] == "玄妙实体"
    )
    assert entity["label"] == "Concept"
    assert not any(
        assertion["predicate_type"] == "HAS_EFFECT"
        for assertion in staged_snapshot["ontology_assertions"].values()
        if assertion["subject_entity_id"] == entity["entity_id"]
    )

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 409, publish_response.text
    assert publish_response.json()["error"]["code"] == "ontology_publish_validation_failed"
    detail_messages = [item["message"] for item in publish_response.json()["error"]["details"]]
    assert any("Unresolved OWL class mapping: 玄妙实体" in item for item in detail_messages)
    assert any("Unresolved OWL property mapping: hasmysterylink" in item for item in detail_messages)


def test_neo4j_provenance_rows_entityize_assertion_evidence_and_document() -> None:
    rows = store.build_neo4j_provenance_rows({"mat_001"})

    assertion_ids = {row["assertion_id"] for row in rows["assertion_rows"]}
    evidence_ids = {row["evidence_id"] for row in rows["evidence_rows"]}
    document_ids = {row["document_id"] for row in rows["document_rows"]}
    support_pairs = {(row["assertion_id"], row["evidence_id"]) for row in rows["support_rows"]}
    document_pairs = {(row["assertion_id"], row["document_id"]) for row in rows["document_link_rows"]}

    assert "assert_seed_fuzi_ctx_tea" in assertion_ids
    assert "evidence_seed_fuzi_001" in evidence_ids
    assert "guide_seed_demo_001" in document_ids
    assert ("assert_seed_fuzi_ctx_tea", "evidence_seed_fuzi_001") in support_pairs
    assert ("assert_seed_fuzi_ctx_tea", "guide_seed_demo_001") in document_pairs


def test_relation_vocabulary_aliases_are_canonicalized() -> None:
    assert canonical_relation_code("CONTRAINDICATED_FOR") == "NOT_FOR_POPULATION"
    assert canonical_relation_code("DISALLOWED_IN") == "PROHIBITED_IN_CONTEXT"
    assert canonical_relation_code("APPLICABLE_IN") == "ALLOWED_IN_CONTEXT"
    assert canonical_relation_code("INCOMPATIBLE_WITH") == "CONTRAINDICATED_WITH"
    assert canonical_relation_code("IS_A") == "SUBCLASS_OF"


def test_query_service_uses_active_kb_version_by_default() -> None:
    query = OntologyQueryService(store)
    old_results = query.query_entities_by_candidates(["附子"], kb_version="kb-2026-05-29-01")
    assert [item.standard_name for item in old_results] == ["附子"]

    old_kb_id = next(
        version_id for version_id, version in store.kb_versions.items()
        if version["version_code"] == "kb-2026-05-29-01"
    )
    old_published_at = store.kb_versions[old_kb_id]["published_at"]
    newer_kb_id = uuid4()
    store.kb_versions[newer_kb_id] = {
        **store.kb_versions[old_kb_id],
        "kb_version_id": newer_kb_id,
        "version_code": "kb-newer-no-fuzi",
        "published_at": old_published_at.replace(year=old_published_at.year + 1),
    }
    default_results = query.query_entities_by_candidates(["附子"])
    assert default_results == []


def test_tcm_core_entities_and_logic_method_formula_path_are_queryable(client, monkeypatch) -> None:
    token = login_admin_token(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )

    response = client.post(
        GUIDELINE_IMPORT_URL,
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
        json={
            "source_uri": "tcm-core.md",
            "source_type": "txt",
            "target_version_code": "kb-tcm-core-001",
            "guide_title": "理法方药测试",
            "guide_text": (
                "四君子汤：证候：脾气虚证；病机：脾气不足；治则：补气健脾；"
                "治法：益气健脾；方剂：四君子汤；性味：甘、温；归经：脾经、肺经；"
                "君药：人参；臣药：白术；佐药：茯苓；使药：甘草；体质：气虚体质；"
                "时令：长夏；剂量：每日一剂。"
            ),
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )
    assert publish_response.status_code == 200, publish_response.text

    labels = {
        entity["label"]
        for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-tcm-core-001"
    }
    assert {
        "Pattern",
        "Pathogenesis",
        "TreatmentPrinciple",
        "TreatmentMethod",
        "Property",
        "Meridian",
        "Constitution",
        "Season",
        "Dose",
        "FormulaRole",
    }.issubset(labels)

    assertions = [
        assertion for assertion in store.ontology_assertions.values()
        if assertion["kb_version"] == "kb-tcm-core-001"
    ]
    predicates = {assertion["predicate_type"] for assertion in assertions}
    assert {
        "INDICATED_FOR_PATTERN",
        "BASED_ON_PATTERN",
        "USES_METHOD",
        "REALIZED_BY_FORMULA",
        "HAS_INGREDIENT",
        "HAS_FORMULA_ROLE",
        "HAS_PROPERTY",
        "ENTERS_MERIDIAN",
        "SUITABLE_FOR_CONSTITUTION",
        "SEASONAL_RELEVANCE",
        "HAS_DOSE",
    }.issubset(predicates)
    property_entities = [
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-tcm-core-001"
        and entity["label"] == "Property"
    ]
    property_categories = {
        entity["standard_name"]: entity["attributes"].get("property_category")
        for entity in property_entities
    }
    assert property_categories["甘"] == "flavor"
    assert property_categories["温"] == "nature"
    nature_flavor_entities = [
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-tcm-core-001"
        and entity["label"] == "NatureFlavor"
    ]
    nature_flavor_categories = {
        entity["standard_name"]: entity["attributes"].get("nature_flavor_category")
        for entity in nature_flavor_entities
    }
    assert nature_flavor_categories["甘"] == "flavor"
    assert nature_flavor_categories["温"] == "nature"
    assert "HAS_NATURE" in predicates
    assert "HAS_FLAVOR" in predicates
    dose_entity = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-tcm-core-001"
        and entity["label"] == "Dose"
        and entity["standard_name"] == "每日一剂"
    )
    assert dose_entity["attributes"]["frequency"] == "daily"
    assert dose_entity["attributes"]["dose_count"] == 1

    query = OntologyQueryService(store)
    paths = query.query_logic_method_formula_paths(
        syndrome_or_pathogenesis="脾气虚证",
        kb_version="kb-tcm-core-001",
    )
    assert paths
    first_path = paths[0]
    assert first_path["pattern"]["standard_name"] == "脾虚"
    assert "脾气虚证" in first_path["pattern"]["aliases"]
    assert first_path["principle"]["standard_name"] == "补气健脾"
    assert first_path["method"]["standard_name"] == "益气健脾"
    assert first_path["formula"]["standard_name"] == "四君子汤"
    role_names = {role for herb in first_path["herbs"] for role in herb["roles"]}
    assert {"monarch", "minister", "assistant", "courier"}.issubset(role_names)
    formula_entity = next(
        entity for entity in store.ontology_entities.values()
        if entity["kb_version"] == "kb-tcm-core-001"
        and entity["label"] == "Formula"
        and entity["standard_name"] == "四君子汤"
    )
    role_assertions = [
        assertion for assertion in assertions
        if assertion["predicate_type"] == "HAS_FORMULA_ROLE"
    ]
    assert role_assertions
    assert all(assertion.get("condition_set_id") for assertion in role_assertions)
    first_role_condition = store.condition_sets[role_assertions[0]["condition_set_id"]]
    formula_conditions = first_role_condition["logic"]["all"]
    assert any(
        item["type"] == "formula"
        and item["normalized_concept_id"] == formula_entity["entity_id"]
        for item in formula_conditions
    )
    ontology_base_service = OntologyBaseService(store)
    scoped_roles = ontology_base_service.list_assertions(
        predicate_type="HAS_FORMULA_ROLE",
        kb_version="kb-tcm-core-001",
        condition_context={"formula_id": formula_entity["entity_id"]},
    )
    unscoped_roles = ontology_base_service.list_assertions(
        predicate_type="HAS_FORMULA_ROLE",
        kb_version="kb-tcm-core-001",
        condition_context={"formula": "不存在的方剂"},
    )
    assert len(scoped_roles) == len(role_assertions)
    assert unscoped_roles == []
