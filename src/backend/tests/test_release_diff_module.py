from __future__ import annotations

from uuid import uuid4

from qihuang_shield.dependencies import store
from qihuang_shield.utils import utcnow


def _login_admin(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"}


def _add_release(version_code: str) -> None:
    now = utcnow()
    version_id = uuid4()
    store.kb_versions[version_id] = {
        "kb_version_id": version_id,
        "version_code": version_code,
        "status": "published",
        "source_type": "test",
        "source_checksum": None,
        "validation_report": {"warnings": 0, "errors": 0},
        "snapshot_uri": f"memory://{version_code}",
        "published_by": None,
        "published_at": now,
        "rollback_from_version_id": None,
        "created_at": now,
        "updated_at": now,
    }


def test_release_diff_reports_added_and_removed_assets(client) -> None:
    token = _login_admin(client)
    _add_release("kb-diff-base-001")
    _add_release("kb-diff-target-001")
    store.ontology_entities["concept_diff_base"] = {
        "entity_id": "concept_diff_base",
        "label": "Formula",
        "standard_name": "旧方",
        "aliases": [],
        "kb_version": "kb-diff-base-001",
        "attributes": {},
    }
    store.ontology_entities["concept_diff_target"] = {
        "entity_id": "concept_diff_target",
        "label": "Formula",
        "standard_name": "新方",
        "aliases": [],
        "kb_version": "kb-diff-target-001",
        "attributes": {},
    }
    store.evidence_sources["evidence_diff_target"] = {
        "evidence_id": "evidence_diff_target",
        "kb_version": "kb-diff-target-001",
        "source_type": "test",
        "source_uri": "test://diff",
        "source_title": "Diff Test",
        "source_text": "新方用于测试。",
        "entity_id": "concept_diff_target",
        "status": "published",
        "document_id": None,
    }

    response = client.get(
        "/api/v1/ontology-base/releases/kb-diff-target-001/diff",
        headers=_headers(token),
        params={"base_release_id": "kb-diff-base-001"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["base_release_code"] == "kb-diff-base-001"
    assert data["target_release_code"] == "kb-diff-target-001"
    assert data["counts"]["concepts"]["added"] == 1
    assert data["counts"]["concepts"]["removed"] == 1
    assert data["sections"]["concepts"]["added"][0]["standard_name"] == "新方"
    assert data["sections"]["concepts"]["removed"][0]["standard_name"] == "旧方"
    assert data["counts"]["evidence"]["added"] == 1


def test_object_timeline_returns_change_records(client) -> None:
    token = _login_admin(client)
    change_id = "chg_timeline_test_001"
    store.change_records[change_id] = {
        "change_id": change_id,
        "object_type": "concept",
        "object_id": "concept_timeline_001",
        "change_type": "review",
        "from_version": "draft",
        "to_version": "published",
        "change_summary": "测试变更记录",
        "reason": "验证 timeline",
        "impact_note": None,
        "created_at": utcnow(),
        "created_by": "tester",
        "review_status": "approved",
    }

    response = client.get(
        "/api/v1/ontology-base/objects/concept_timeline_001/timeline",
        headers=_headers(token),
        params={"object_type": "concept"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["object_id"] == "concept_timeline_001"
    assert data["object_type"] == "concept"
    assert [item["change_id"] for item in data["change_records"]] == [change_id]
