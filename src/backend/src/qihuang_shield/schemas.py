from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import (
    ContentType,
    Decision,
    EvidenceType,
    RiskLevel,
    RoleCode,
    RuleType,
    Scenario,
)


class BaseSchema(BaseModel):
    class Config:
        use_enum_values = True


class ErrorDetail(BaseSchema):
    field: str | None = None
    message: str


class ErrorInfo(BaseSchema):
    code: str
    message: str
    retryable: bool = False
    details: list[ErrorDetail] = Field(default_factory=list)


class MetaInfo(BaseSchema):
    page: int | None = None
    page_size: int | None = None
    total: int | None = None
    total_pages: int | None = None


class UserProfile(BaseSchema):
    user_id: UUID
    email: str
    display_name: str
    roles: list[RoleCode] = Field(default_factory=list)


class TenantRole(BaseSchema):
    tenant_id: UUID
    tenant_code: str
    role: RoleCode


class CurrentUserProfile(UserProfile):
    tenant_roles: list[TenantRole] = Field(default_factory=list)
    current_tenant_id: UUID | None = None
    current_tenant_code: str | None = None


class RequestContext(BaseSchema):
    trace_id: str
    actor_type: Literal["user", "api_client"] = "user"
    actor_user_id: UUID | None = None
    actor_client_id: UUID | None = None
    tenant_id: UUID | None = None
    tenant_code: str | None = None
    roles: list[RoleCode] = Field(default_factory=list)
    auth_method: Literal["bearer", "api_key", "oauth"] = "bearer"
    user: CurrentUserProfile | None = None


class PermissionDecision(BaseSchema):
    allowed: bool
    action: str
    resource: str
    reason: str | None = None


class LoginRequest(BaseSchema):
    email: str
    password: str


class LoginResponseData(BaseSchema):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = 7200
    user: UserProfile


class ExtractedEntity(BaseSchema):
    text: str
    standard_name: str
    type: str
    start: int
    end: int
    confidence: float
    entity_id: str | None = None


class EvidenceSpan(BaseSchema):
    text: str
    start: int
    end: int
    rule_id: str | None = None
    entity_id: str | None = None
    evidence_type: EvidenceType = EvidenceType.RAW_TEXT


class OntologyFact(BaseSchema):
    subject: str
    relation: str
    object: str
    kb_version: str
    assertion_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    document_id: str | None = None
    source_uri: str | None = None
    source_title: str | None = None
    snapshot_uri: str | None = None


class SemanticTrace(BaseSchema):
    mention_id: str | None = None
    normalization_decision_id: str | None = None
    concept_id: str | None = None
    assertion_id: str | None = None
    condition_set_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    projection_type: str | None = None
    projection_version: str | None = None


class KnowledgeCard(BaseSchema):
    entity: dict[str, Any]
    aliases: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    diseases: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    treatment_methods: list[str] = Field(default_factory=list)
    usage_methods: list[str] = Field(default_factory=list)
    not_for_populations: list[str] = Field(default_factory=list)
    allowed_contexts: list[str] = Field(default_factory=list)
    prohibited_contexts: list[str] = Field(default_factory=list)
    contraindications: list[dict[str, Any]] = Field(default_factory=list)
    kb_version: str
    assertion_count: int = 0
    evidence_count: int = 0
    derived_from_assertions: bool = False
    projection_type: Literal["knowledge_card"] = "knowledge_card"
    projection_version: str = "projection-v1"


class KnowledgeCardProjection(KnowledgeCard):
    """Read model projected from concepts/assertions/evidence for UI consumption."""


class OntologyAssertionView(BaseSchema):
    assertion_id: str
    subject_entity_id: str
    predicate_type: str
    object_entity_id: str | None = None
    object_value: str | None = None
    kb_version: str
    status: str
    evidence_ids: list[str] = Field(default_factory=list)
    document_id: str | None = None
    review_status: str | None = None
    review_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class EvidenceSourceView(BaseSchema):
    evidence_id: str
    kb_version: str
    source_type: str
    source_uri: str | None = None
    source_title: str | None = None
    source_text: str
    entity_id: str | None = None
    status: str
    document_id: str | None = None


class GuidelineDocumentView(BaseSchema):
    document_id: str
    kb_version: str
    source_uri: str | None = None
    title: str | None = None
    source_type: str
    status: str


class KnowledgeCardDetail(KnowledgeCard):
    assertions: list[OntologyAssertionView] = Field(default_factory=list)
    evidence_sources: list[EvidenceSourceView] = Field(default_factory=list)
    guideline_documents: list[GuidelineDocumentView] = Field(default_factory=list)
    concept_id: str | None = None


class OntologyConceptDetail(BaseSchema):
    concept: OntologyEntityView
    assertions: list[OntologyAssertionView] = Field(default_factory=list)
    evidence_sources: list[EvidenceSourceView] = Field(default_factory=list)
    guideline_documents: list[GuidelineDocumentView] = Field(default_factory=list)
    related_diseases: list[OntologyEntityView] = Field(default_factory=list)
    related_symptoms: list[OntologyEntityView] = Field(default_factory=list)
    related_patterns: list[OntologyEntityView] = Field(default_factory=list)
    related_principles: list[OntologyEntityView] = Field(default_factory=list)
    related_methods: list[OntologyEntityView] = Field(default_factory=list)
    related_formulas: list[OntologyEntityView] = Field(default_factory=list)
    related_herbs: list[OntologyEntityView] = Field(default_factory=list)
    related_usage_methods: list[OntologyEntityView] = Field(default_factory=list)




class OntologyVersionView(BaseSchema):
    version_id: str
    version_type: str
    version_name: str
    based_on_version: str | None = None
    change_summary: str | None = None
    change_scope: list[str] = Field(default_factory=list)
    created_at: datetime
    created_by: str
    review_status: str
    reviewed_by: str | None = None
    published_at: datetime | None = None
    status: str


class RelationDefinitionView(BaseSchema):
    relation_code: str
    display_name_zh: str
    definition: str
    domain: list[str] = Field(default_factory=list)
    range: list[str] = Field(default_factory=list)
    semantic_direction: str | None = None
    inverse_relation: str | None = None
    boundary_note: str | None = None
    condition_note: str | None = None
    schema_version: str
    status: str


class ConditionSetView(BaseSchema):
    condition_set_id: str
    logic: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class EvidenceLinkView(BaseSchema):
    link_id: str
    target_type: str
    target_id: str
    evidence_id: str
    support_role: str
    support_strength: str
    note: str | None = None


class ChangeRecordView(BaseSchema):
    change_id: str
    object_type: str
    object_id: str
    change_type: str
    from_version: str | None = None
    to_version: str
    change_summary: str
    reason: str | None = None
    impact_note: str | None = None
    created_at: datetime
    created_by: str
    review_status: str



class AssertionBundleView(BaseSchema):
    assertion: OntologyAssertionView
    condition: ConditionSetView | None = None
    evidence_sources: list[EvidenceSourceView] = Field(default_factory=list)
    evidence_links: list[EvidenceLinkView] = Field(default_factory=list)
    change_records: list[ChangeRecordView] = Field(default_factory=list)


class ConceptBundleView(BaseSchema):
    concept: OntologyEntityView
    assertions: list[OntologyAssertionView] = Field(default_factory=list)
    evidence_sources: list[EvidenceSourceView] = Field(default_factory=list)


class ConceptSearchResultView(BaseSchema):
    concept: OntologyEntityView
    matched_text: str
    match_type: str
    assertion_count: int = 0
    evidence_count: int = 0


class ConceptVerificationView(BaseSchema):
    concept: OntologyEntityView
    release_code: str | None = None
    assertions: list[AssertionBundleView] = Field(default_factory=list)
    evidence_sources: list[EvidenceSourceView] = Field(default_factory=list)
    change_records: list[ChangeRecordView] = Field(default_factory=list)
    related_concepts: list[OntologyEntityView] = Field(default_factory=list)


class ReleaseDiffSectionView(BaseSchema):
    added: list[dict[str, Any]] = Field(default_factory=list)
    removed: list[dict[str, Any]] = Field(default_factory=list)
    common_count: int = 0


class ReleaseDiffView(BaseSchema):
    base_release_code: str | None = None
    target_release_code: str
    sections: dict[str, ReleaseDiffSectionView] = Field(default_factory=dict)
    counts: dict[str, dict[str, int]] = Field(default_factory=dict)


class ObjectTimelineView(BaseSchema):
    object_id: str
    object_type: str | None = None
    change_records: list[ChangeRecordView] = Field(default_factory=list)



class OntologyValidationIssueView(BaseSchema):
    severity: str
    code: str
    message: str
    object_type: str
    object_id: str | None = None


class OntologyValidationReportView(BaseSchema):
    status: str
    issue_count: int
    issues: list[OntologyValidationIssueView] = Field(default_factory=list)

class MentionView(BaseSchema):
    mention_id: str
    source_type: str
    source_record_id: str
    surface_text: str
    normalized_text: str
    start_offset: int
    end_offset: int
    mention_type_guess: str | None = None
    context_window: str | None = None
    kb_version: str | None = None
    created_at: datetime


class NormalizationDecisionView(BaseSchema):
    decision_id: str
    mention_id: str
    resolved_concept_id: str | None = None
    canonical_name: str | None = None
    resolver_type: str
    resolver_version: str = "normalizer-v1"
    confidence_score: float = 0.0
    candidate_list: list[dict[str, Any]] = Field(default_factory=list)
    decision_reason: str | None = None
    status: str = "resolved"
    kb_version: str | None = None
    created_at: datetime


class NormalizationDecisionReviewRequest(BaseSchema):
    status: Literal["resolved", "rejected"]
    resolved_concept_id: str | None = None
    canonical_name: str | None = None
    create_alias: bool = False
    reason: str = Field(..., min_length=1)
    operator_id: str = Field(default="system")


class NormalizationDecisionBatchReviewRequest(NormalizationDecisionReviewRequest):
    decision_ids: list[str] = Field(..., min_length=1)


class ConceptAliasReviewRequest(BaseSchema):
    status: Literal["published", "rejected"]
    reason: str = Field(..., min_length=1)
    operator_id: str = Field(default="system")


class ConceptProposalCreateRequest(BaseSchema):
    concept_type: str = Field(..., min_length=1)
    standard_name: str = Field(..., min_length=1)
    definition: str = Field(..., min_length=1)
    evidence_ids: list[str] = Field(..., min_length=1)
    source_note: str | None = None
    operator_id: str = Field(default="system")


class ConceptProposalReviewRequest(BaseSchema):
    status: Literal["approved", "rejected"]
    reason: str = Field(..., min_length=1)
    operator_id: str = Field(default="system")


class StagedAssertionReviewRequest(BaseSchema):
    status: Literal["accepted", "rejected"]
    reason: str = Field(..., min_length=1)
    operator_id: str = Field(default="system")


class ConceptProposalView(BaseSchema):
    proposal_id: str
    decision_id: str
    mention_id: str
    surface_text: str
    concept_type: str
    standard_name: str
    definition: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_sources: list[dict[str, Any]] = Field(default_factory=list)
    source_note: str | None = None
    status: str
    proposed_concept_id: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    review_reason: str | None = None


class TerminologyPublishRequest(BaseSchema):
    version_id: str = Field(..., min_length=1)
    version_name: str = Field(..., min_length=1)
    alias_ids: list[str] = Field(..., min_length=1)
    change_summary: str
    operator_id: str = Field(default="system")


class RuleCreateRequest(BaseSchema):
    rule_code: str = Field(..., min_length=1, max_length=32)
    rule_name: str = Field(..., min_length=1, max_length=128)
    rule_type: RuleType
    description: str | None = None


class RuleVersionCreateRequest(BaseSchema):
    version_no: str = Field(..., min_length=1, max_length=32)
    priority: int = Field(..., ge=0, le=1000)
    default_decision: Decision
    risk_level: RiskLevel
    conditions: dict[str, Any]
    action: dict[str, Any]
    explanation_template: str = Field(..., min_length=1)


class RuleView(BaseSchema):
    rule_id: UUID
    rule_code: str
    rule_name: str
    rule_type: RuleType
    status: str
    description: str | None = None


class RuleVersionView(BaseSchema):
    rule_version_id: UUID
    rule_id: UUID
    version_no: str
    status: str
    priority: int
    default_decision: str
    risk_level: str
    explanation_template: str


class PolicyRuleOverrideInput(BaseSchema):
    rule_code: str
    enabled: bool = True
    override_decision: Decision | None = None
    override_risk_level: RiskLevel | None = None


class PolicyCreateRequest(BaseSchema):
    tenant_id: UUID
    policy_code: str = Field(..., min_length=1, max_length=64)
    policy_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None


class PolicyVersionCreateRequest(BaseSchema):
    version_no: int = Field(..., ge=1)
    scenario_scope: list[Scenario] = Field(default_factory=list)
    content_type_scope: list[ContentType] = Field(default_factory=list)
    fallback_mode: str = Field(default="review_first")
    low_confidence_decision: Decision = Decision.REVIEW
    config: dict[str, Any] = Field(default_factory=dict)
    rule_overrides: list[PolicyRuleOverrideInput] = Field(default_factory=list)


class PolicyView(BaseSchema):
    policy_id: UUID
    tenant_id: UUID
    policy_code: str
    policy_name: str
    status: str
    description: str | None = None


class PolicyVersionView(BaseSchema):
    policy_version_id: UUID
    policy_id: UUID
    version_no: int
    status: str
    fallback_mode: str
    low_confidence_decision: str


class OntologyImportCreateRequest(BaseSchema):
    source_uri: str
    source_type: str
    target_version_code: str
    guide_title: str | None = None
    guide_text: str | None = None
    guide_file_name: str | None = None
    guide_file_base64: str | None = None


class OntologyImportJobView(BaseSchema):
    import_job_id: UUID
    kb_version_id: UUID
    status: str
    source_uri: str
    source_type: str
    warning_count: int
    error_count: int
    validation_report: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    finished_at: datetime | None = None


class ImportGovernanceIssueView(BaseSchema):
    issue_id: str
    severity: str
    status: str
    code: str
    title: str
    message: str
    object_type: str
    object_id: str | None = None
    action: str
    mention_id: str | None = None
    surface_text: str | None = None
    candidate_list: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_sources: list[dict[str, Any]] = Field(default_factory=list)
    resolved_concept_id: str | None = None
    canonical_name: str | None = None


class ImportGovernanceSummaryView(BaseSchema):
    concepts: int = 0
    assertions: int = 0
    evidence: int = 0
    mentions: int = 0
    normalizations: int = 0
    issue_count: int = 0
    issue_counts_by_severity: dict[str, int] = Field(default_factory=dict)
    issue_counts_by_status: dict[str, int] = Field(default_factory=dict)


class ImportGovernanceView(BaseSchema):
    import_job: OntologyImportJobView
    release_code: str
    summary: ImportGovernanceSummaryView
    issues: list[ImportGovernanceIssueView] = Field(default_factory=list)
    staged_assertions: list[AssertionBundleView] = Field(default_factory=list)
    concept_proposals: list[ConceptProposalView] = Field(default_factory=list)


class KnowledgeReleaseView(BaseSchema):
    release_id: UUID
    release_code: str
    kb_version_id: UUID
    status: str
    source_type: str
    timestamps: dict[str, datetime | None] = Field(default_factory=dict)
    published_at: datetime | None = None
    validation_report: dict[str, Any] = Field(default_factory=dict)
    component_counts: dict[str, int] = Field(default_factory=dict)
    projection_count: int = 0


class OntologyEntityView(BaseSchema):
    entity_id: str
    label: str
    standard_name: str
    aliases: list[str] = Field(default_factory=list)
    kb_version: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class VectorUpsertRequest(BaseSchema):
    doc_id: str = Field(..., min_length=1, max_length=128)
    text: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorSearchRequest(BaseSchema):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class SuccessEnvelope(BaseSchema):
    status: Literal["success"] = "success"
    trace_id: str
    data: Any = None
    meta: MetaInfo | None = None


class ErrorEnvelope(BaseSchema):
    status: Literal["error"] = "error"
    trace_id: str
    error: ErrorInfo
