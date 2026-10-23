from __future__ import annotations

from qihuang_shield.dependencies import ontology_service


GOVERNANCE_URL = "/api/v1/ontology/import-jobs/{}/governance"


def login_admin_token(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def import_guideline(client, monkeypatch, *, target_version_code: str, guide_text: str) -> tuple[str, str]:
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
            "source_uri": f"{target_version_code}.md",
            "source_type": "txt",
            "target_version_code": target_version_code,
            "guide_title": "导入治理测试",
            "guide_text": guide_text,
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    return token, import_job_id


def test_import_governance_returns_normal_import_summary(client, monkeypatch) -> None:
    token, import_job_id = import_guideline(
        client,
        monkeypatch,
        target_version_code="kb-governance-normal-001",
        guide_text="附子：功效：回阳救逆。",
    )

    response = client.get(
        GOVERNANCE_URL.format(import_job_id),
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    summary = data["summary"]
    assert data["import_job"]["import_job_id"] == import_job_id
    assert data["release_code"] == "kb-governance-normal-001"
    assert summary["concepts"] >= 1
    assert summary["assertions"] >= 1
    assert summary["evidence"] >= 1
    assert summary["mentions"] >= 1
    assert summary["normalizations"] >= 1
    assert not [issue for issue in data["issues"] if issue["object_type"] == "normalization_decision"]
    assert summary["issue_count"] == len(data["issues"])
    assert all(
        set(issue) == {
            "issue_id",
            "severity",
            "status",
            "code",
            "title",
            "message",
            "object_type",
            "object_id",
            "action",
        }
        for issue in data["issues"]
    )


def test_import_governance_exposes_unresolved_normalization_issue(client, monkeypatch) -> None:
    token, import_job_id = import_guideline(
        client,
        monkeypatch,
        target_version_code="kb-governance-unresolved-001",
        guide_text="附子：证候：月光虚证；禁用于孕妇。",
    )

    response = client.get(
        GOVERNANCE_URL.format(import_job_id),
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    unresolved = [
        issue
        for issue in data["issues"]
        if issue["object_type"] == "normalization_decision" and issue["status"] == "unresolved"
    ]
    assert unresolved
    assert unresolved[0]["severity"] == "warning"
    assert unresolved[0]["title"] == "Unresolved normalization decision"
    assert unresolved[0]["action"] == "resolve_normalization"
    assert "月光虚证" in unresolved[0]["message"]
    assert data["summary"]["issue_counts_by_status"]["unresolved"] == len(unresolved)


def test_import_governance_returns_not_found_for_missing_job(client) -> None:
    token = login_admin_token(client)

    response = client.get(
        GOVERNANCE_URL.format("00000000-0000-0000-0000-000000000000"),
        headers={"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"},
    )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "not_found"
