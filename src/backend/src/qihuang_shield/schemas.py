from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from .enums import (
    BatchStatus,
    ContentType,
    Decision,
    EvidenceType,
    FeedbackType,
    RecommendedAction,
    ReviewTaskStatus,
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


class LoginRequest(BaseSchema):
    email: str
    password: str


class LoginResponseData(BaseSchema):
    access_token: str
    token_type: Literal["Bearer"] = "Bearer"
    expires_in: int = 7200
    user: UserProfile


class ModerationMetadata(BaseSchema):
    author_id: str | None = None
    source: str | None = None


class ModerationSyncRequest(BaseSchema):
    content_id: str = Field(..., min_length=1, max_length=128)
    content_text: str = Field(..., min_length=1)
    content_type: ContentType = ContentType.OTHER
    scenario: Scenario = Scenario.OTHER
    policy_id: str | None = None
    tenant_id: str = Field(..., min_length=1, max_length=64)
    metadata: ModerationMetadata = Field(default_factory=ModerationMetadata)


class RuleHit(BaseSchema):
    rule_id: str
    rule_name: str
    rule_version: str
    risk_level: str
    decision: str
    reason: str


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


class ModerationSyncResponse(BaseSchema):
    status: Literal["success"] = "success"
    trace_id: str
    content_id: str
    decision: str
    risk_level: str
    confidence: float
    fallback_triggered: bool = False
    hit_rules: list[RuleHit] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    ontology_facts: list[OntologyFact] = Field(default_factory=list)
    explanation: str
    recommended_action: str


class BatchItemRequest(BaseSchema):
    content_id: str = Field(..., min_length=1, max_length=128)
    content_text: str = Field(..., min_length=1)
    content_type: ContentType = ContentType.OTHER
    scenario: Scenario = Scenario.OTHER
    metadata: ModerationMetadata = Field(default_factory=ModerationMetadata)


class CreateBatchRequest(BaseSchema):
    batch_name: str | None = None
    tenant_id: str = Field(..., min_length=1, max_length=64)
    policy_id: str | None = None
    callback_url: str | None = None
    items: list[BatchItemRequest] = Field(..., min_length=1)


class BatchCreateData(BaseSchema):
    batch_id: UUID
    status: BatchStatus
    total_count: int
    query_url: str


class BatchStatusData(BaseSchema):
    batch_id: UUID
    status: BatchStatus
    total_count: int
    processed_count: int
    success_count: int
    failed_count: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class BatchItemResult(BaseSchema):
    request_id: UUID
    trace_id: str
    content_id: str
    decision: str
    risk_level: str
    fallback_triggered: bool = False
    created_at: datetime


class ReviewTaskListItem(BaseSchema):
    task_id: UUID
    content_id: str
    decision: str
    risk_level: str
    hit_rules: list[str] = Field(default_factory=list)
    status: ReviewTaskStatus
    created_at: datetime


class ReviewTaskAssignee(BaseSchema):
    user_id: UUID
    display_name: str


class KnowledgeCard(BaseSchema):
    entity: dict[str, Any]
    aliases: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    not_for_populations: list[str] = Field(default_factory=list)
    allowed_contexts: list[str] = Field(default_factory=list)
    prohibited_contexts: list[str] = Field(default_factory=list)
    contraindications: list[dict[str, Any]] = Field(default_factory=list)
    kb_version: str


class ReviewTaskDetail(BaseSchema):
    task_id: UUID
    status: ReviewTaskStatus
    content_id: str
    content_text: str
    decision: str
    risk_level: str
    assignee: ReviewTaskAssignee | None = None
    hit_rules: list[RuleHit] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    ontology_facts: list[OntologyFact] = Field(default_factory=list)
    knowledge_card: KnowledgeCard | None = None
    feedback: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class ClaimReviewTaskRequest(BaseSchema):
    operator_user_id: UUID


class SubmitReviewTaskRequest(BaseSchema):
    operator_user_id: UUID
    final_decision: Decision
    final_action: RecommendedAction
    overwrite_system_decision: bool = False
    resolution_reason: str
    resolution_note: str | None = None


class FeedbackCreateRequest(BaseSchema):
    feedback_type: FeedbackType
    target_rule_id: UUID | None = None
    target_entity_ref_id: str | None = None
    comment: str | None = None
    labels: dict[str, Any] = Field(default_factory=dict)


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


class OntologyEntityView(BaseSchema):
    entity_id: str
    label: str
    standard_name: str
    aliases: list[str] = Field(default_factory=list)
    kb_version: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class ReportOverview(BaseSchema):
    total_requests: int
    decision_distribution: dict[str, int]
    review_completion_rate: float
    overwrite_rate: float
    api_p95_ms: int
    fallback_rate: float


class RuleHitReportItem(BaseSchema):
    rule_code: str
    rule_name: str
    hit_count: int
    block_count: int
    review_count: int


class ReviewQualityReport(BaseSchema):
    total_review_tasks: int
    completed_review_tasks: int
    feedback_counts: dict[str, int]
    overwrite_count: int
    overwrite_rate: float


class SuccessEnvelope(BaseSchema):
    status: Literal["success"] = "success"
    trace_id: str
    data: Any = None
    meta: MetaInfo | None = None


class ErrorEnvelope(BaseSchema):
    status: Literal["error"] = "error"
    trace_id: str
    error: ErrorInfo
