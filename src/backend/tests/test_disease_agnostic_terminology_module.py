from __future__ import annotations

from pathlib import Path
from uuid import UUID

from qihuang_shield.dependencies import ontology_service, store
from qihuang_shield.services.guideline_import import GuidelineOntologyExtractor
from qihuang_shield.services.terminology import StoreTerminologyResolver


def _login_admin(client) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Code": "tenant_demo"}


def test_unknown_disease_enters_unresolved_then_concept_proposal_without_code_terms(client, monkeypatch) -> None:
    token = _login_admin(client)
    monkeypatch.setattr(
        ontology_service.vector_search_service,
        "index_knowledge_assets",
        lambda **_: {"indexed_count": 0, "guide_chunk_count": 0, "knowledge_card_count": 0, "documents": []},
    )
    response = client.post(
        "/api/v1/ontology/guideline-imports",
        headers=_headers(token),
        json={
            "source_uri": "asthma-disease-agnostic.md",
            "source_type": "txt",
            "target_version_code": "kb-disease-agnostic-001",
            "guide_title": "疾病无关术语测试",
            "guide_text": "麻黄汤：疾病：哮病；症状：喘鸣；功效：宣肺平喘。",
        },
    )
    assert response.status_code == 200, response.text
    import_job_id = response.json()["data"]["import_job"]["import_job_id"]
    job = store.import_jobs[UUID(import_job_id)]
    staged = job["staged_snapshot"]
    unresolved = [
        decision for decision in staged["normalization_decisions"].values()
        if decision["status"] == "unresolved"
    ]
    unresolved_terms = {
        staged["mentions"][decision["mention_id"]]["surface_text"]
        for decision in unresolved
    }
    assert {"哮病", "喘鸣"}.issubset(unresolved_terms)

    disease_decision = next(
        decision for decision in unresolved
        if staged["mentions"][decision["mention_id"]]["surface_text"] == "哮病"
    )
    evidence_id = next(iter(staged["evidence_sources"]))
    proposal_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/normalizations/{disease_decision['decision_id']}/concept-proposals",
        headers=_headers(token),
        json={
            "concept_type": "Disease",
            "standard_name": "哮病",
            "definition": "以喘促、喉中哮鸣为主要表现的疾病候选概念。",
            "evidence_ids": [evidence_id],
            "operator_id": "curator_001",
        },
    )
    assert proposal_response.status_code == 200, proposal_response.text
    proposal_id = proposal_response.json()["data"]["proposal_id"]
    approve_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/concept-proposals/{proposal_id}/review",
        headers=_headers(token),
        json={"status": "approved", "reason": "证据支持新增疾病概念", "operator_id": "curator_002"},
    )
    assert approve_response.status_code == 200, approve_response.text
    concept_id = approve_response.json()["data"]["proposed_concept_id"]
    assert concept_id in staged["ontology_entities"]
    assert staged["normalization_decisions"][disease_decision["decision_id"]]["status"] == "resolved"

    publish_response = client.post(
        f"/api/v1/ontology/import-jobs/{import_job_id}/publish",
        headers=_headers(token),
    )
    assert publish_response.status_code == 200, publish_response.text
    assert store.ontology_entities[concept_id]["standard_name"] == "哮病"
    assert store.ontology_entities[concept_id]["label"] == "Disease"


def test_content_terms_are_resolved_from_terminology_data_not_code_synonym_tables(client) -> None:
    extractor = GuidelineOntologyExtractor(StoreTerminologyResolver(store))
    assert extractor._canonicalize_disease("哮病") is None
    assert extractor._canonicalize_pattern("脾气虚证") == "脾虚"
    assert "哮病" not in extractor._extract_terminology_hits("麻黄汤用于哮病", {"Disease"})
    assert "脾虚" in extractor._extract_terminology_hits("四君子汤适用于脾气虚证", {"Pattern"})


def test_guideline_import_no_longer_uses_static_disease_symptom_pattern_synonym_hits() -> None:
    extractor = GuidelineOntologyExtractor()
    assert extractor._canonicalize_disease("高血压") is None
    assert extractor._canonicalize_symptom("咳嗽") is None
    assert extractor._canonicalize_pattern("阳虚") is None


def test_guideline_import_has_no_static_disease_symptom_pattern_tables() -> None:
    source = Path("src/qihuang_shield/services/guideline_import.py").read_text(encoding="utf-8")
    forbidden_tokens = [
        "DISEASE_SYNONYMS",
        "SYMPTOM_SYNONYMS",
        "PATTERN_SYNONYMS",
        "hypertension",
        "diabetes",
        "gastritis",
        "cough",
        "yang_deficiency_pattern",
        "spleen_deficiency_pattern",
    ]
    assert not [token for token in forbidden_tokens if token in source]


def test_guideline_import_canonicalizers_do_not_read_static_synonym_tables() -> None:
    source = Path("src/qihuang_shield/services/guideline_import.py").read_text(encoding="utf-8")
    forbidden_snippets = [
        "return self._canonicalize_synonym(value, DISEASE_SYNONYMS)",
        "return self._canonicalize_synonym(value, SYMPTOM_SYNONYMS)",
        "return self._canonicalize_synonym(value, PATTERN_SYNONYMS)",
        "return self._canonicalize_synonym(value, USAGE_METHOD_SYNONYMS)",
        "return self._canonicalize_synonym(value, MERIDIAN_SYNONYMS)",
        "return self._canonicalize_synonym(value, CONSTITUTION_SYNONYMS)",
        "return self._canonicalize_synonym(value, SEASON_SYNONYMS)",
        "return self._canonicalize_synonym(value, PROPERTY_SYNONYMS)",
        "_extract_synonym_hits(clause, PROPERTY_SYNONYMS)",
        "_extract_synonym_hits(clause, USAGE_METHOD_SYNONYMS)",
    ]
    assert not [snippet for snippet in forbidden_snippets if snippet in source]
