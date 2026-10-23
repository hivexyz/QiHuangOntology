from __future__ import annotations

from uuid import uuid4

from qihuang_shield.dependencies import store
from qihuang_shield.utils import utcnow


def login_admin_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def add_draft_release() -> tuple[str, str]:
    kb_version_id = uuid4()
    release_code = "kb-draft-release-001"
    now = utcnow()
    store.kb_versions[kb_version_id] = {
        "kb_version_id": kb_version_id,
        "version_code": release_code,
        "status": "draft",
        "source_type": "guideline",
        "validation_report": {"warnings": 1, "errors": 0},
        "published_at": None,
        "created_at": now,
        "updated_at": now,
    }
    return str(kb_version_id), release_code


def test_list_releases_includes_draft_and_published_assets(client) -> None:
    token = login_admin_token(client)
    draft_id, draft_code = add_draft_release()
    store.knowledge_card_projections["projection_release_test"] = {
        "kb_version": "kb-2026-05-29-01",
        "projection_type": "knowledge_card",
    }

    response = client.get(
        "/api/v1/ontology-base/releases",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )

    assert response.status_code == 200, response.text
    releases = response.json()["data"]
    by_code = {release["release_code"]: release for release in releases}
    published = by_code["kb-2026-05-29-01"]
    draft = by_code[draft_code]
    assert published["status"] == "published"
    assert draft["status"] == "draft"
    assert draft["release_id"] == draft_id
    assert published["component_counts"]["concepts"] > 0
    assert published["component_counts"]["assertions"] > 0
    assert published["projection_count"] > 0
    assert set(published["timestamps"]) == {"created_at", "updated_at"}


def test_get_release_by_uuid_and_version_code(client) -> None:
    token = login_admin_token(client)
    published_id = next(
        str(version["kb_version_id"])
        for version in store.kb_versions.values()
        if version["version_code"] == "kb-2026-05-29-01"
    )
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"}

    by_uuid = client.get(f"/api/v1/ontology-base/releases/{published_id}", headers=headers)
    by_code = client.get("/api/v1/ontology-base/releases/kb-2026-05-29-01", headers=headers)

    assert by_uuid.status_code == 200, by_uuid.text
    assert by_code.status_code == 200, by_code.text
    assert by_uuid.json()["data"] == by_code.json()["data"]


def test_get_release_returns_not_found_for_missing_id(client) -> None:
    token = login_admin_token(client)

    response = client.get(
        "/api/v1/ontology-base/releases/not-a-release",
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
