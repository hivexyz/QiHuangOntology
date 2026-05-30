from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from ..enums import (
    BatchStatus,
    Decision,
    RecommendedAction,
    RiskLevel,
    ReviewTaskStatus,
    Scenario,
)
from ..exceptions import APIError
from ..schemas import (
    BatchCreateData,
    BatchItemRequest,
    BatchItemResult,
    BatchStatusData,
    CreateBatchRequest,
    EvidenceSpan,
    ExtractedEntity,
    ModerationSyncRequest,
    ModerationSyncResponse,
    OntologyFact,
    ReviewTaskDetail,
    ReviewTaskListItem,
    RuleHit,
)
from ..store import InMemoryStore
from ..utils import display_decision, display_risk_level, new_trace_id, utcnow


@dataclass(slots=True)
class ModerationMatch:
    rule_code: str
    rule_name: str
    decision: Decision
    risk_level: RiskLevel
    reason: str
    entities: list[ExtractedEntity]
    evidence_spans: list[EvidenceSpan]
    ontology_facts: list[OntologyFact]


class ModerationService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def moderate_sync(
        self,
        payload: ModerationSyncRequest,
        *,
        trace_id: str | None = None,
    ) -> ModerationSyncResponse:
        response, _ = self._moderate(payload, trace_id=trace_id)
        return response

    def _moderate(
        self,
        payload: ModerationSyncRequest,
        *,
        trace_id: str | None = None,
        batch_id: UUID | None = None,
    ) -> tuple[ModerationSyncResponse, UUID]:
        if not payload.content_text.strip():
            raise APIError(status_code=400, code="invalid_request", message="content_text is required")
        if len(payload.content_text) > 5000:
            raise APIError(status_code=413, code="content_too_large", message="content_text is too large")

        started_at = perf_counter()
        request_id = uuid4()
        trace_id = trace_id or new_trace_id()
        now = utcnow()
        scenario = self._as_scenario(payload.scenario)
        content_type = self._enum_value(payload.content_type)
        tenant_id = self._resolve_tenant_id(payload.tenant_id)
        client_id = self._default_client_id_for_tenant(tenant_id)
        policy_version = self._resolve_policy_version(payload.policy_id)
        kb_version = self._published_kb_version()

        matches = self._evaluate_text(payload.content_text, scenario)
        decision, risk_level, recommended_action, explanation = self._summarize(matches)
        hit_rules = [
            RuleHit(
                rule_id=match.rule_code,
                rule_name=match.rule_name,
                rule_version="1.0.0",
                risk_level=display_risk_level(match.risk_level),
                decision=display_decision(match.decision),
                reason=match.reason,
            )
            for match in matches
        ]
        entities = self._unique_entities(matches)
        evidence_spans = self._unique_evidence(matches)
        ontology_facts = self._unique_facts(matches)
        confidence = self._confidence(matches)
        latency_ms = int((perf_counter() - started_at) * 1000)

        request_record = {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "client_id": client_id,
            "batch_id": batch_id,
            "policy_version_id": policy_version["policy_version_id"] if policy_version else None,
            "trace_id": trace_id,
            "content_id": payload.content_id,
            "request_mode": "sync",
            "content_type": content_type,
            "scenario": scenario.value,
            "content_text": payload.content_text,
            "content_text_hash": sha256(payload.content_text.encode("utf-8")).hexdigest(),
            "metadata_json": payload.metadata.model_dump(),
            "idempotency_key": None,
            "created_at": now,
            "updated_at": now,
        }
        result_id = uuid4()
        result_record = {
            "result_id": result_id,
            "request_id": request_id,
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "content_id": payload.content_id,
            "content_text": payload.content_text,
            "content_type": content_type,
            "scenario": scenario.value,
            "kb_version_id": kb_version["kb_version_id"],
            "policy_version_id": policy_version["policy_version_id"] if policy_version else None,
            "decision": decision.value,
            "risk_level": risk_level.value,
            "confidence": confidence,
            "recommended_action": recommended_action.value,
            "fallback_triggered": False,
            "fallback_reason": None,
            "prompt_version": "prompt-v1",
            "model_version": "demo-model-v1",
            "latency_ms": latency_ms,
            "explanation": explanation,
            "hit_rules": [item.model_dump() for item in hit_rules],
            "entities": [item.model_dump() for item in entities],
            "evidence_spans": [item.model_dump() for item in evidence_spans],
            "ontology_facts": [item.model_dump() for item in ontology_facts],
            "created_at": now,
            "updated_at": now,
        }

        with self.store.lock():
            self.store.requests[request_id] = request_record
            self.store.results[result_id] = result_record
            self.store.result_by_request_id[request_id] = result_id
            created_review_task = None
            if decision in {Decision.REVIEW, Decision.BLOCK}:
                created_review_task = self._create_review_task(result_record, tenant_id, now)
        self.store.persist_moderation_bundle(request_record, result_record, None, created_review_task)

        response = ModerationSyncResponse(
            trace_id=trace_id,
            content_id=payload.content_id,
            decision=display_decision(decision),
            risk_level=display_risk_level(risk_level),
            confidence=confidence,
            fallback_triggered=False,
            hit_rules=hit_rules,
            entities=entities,
            evidence_spans=evidence_spans,
            ontology_facts=ontology_facts,
            explanation=explanation,
            recommended_action=recommended_action.value,
        )
        return response, request_id

    def create_batch(self, payload: CreateBatchRequest) -> BatchCreateData:
        tenant_id = self._resolve_tenant_id(payload.tenant_id)
        client_id = self._default_client_id_for_tenant(tenant_id)
        now = utcnow()
        batch_id = uuid4()
        batch_record = {
            "batch_id": batch_id,
            "tenant_id": tenant_id,
            "client_id": client_id,
            "batch_name": payload.batch_name,
            "callback_url": payload.callback_url,
            "status": BatchStatus.RUNNING.value,
            "total_count": len(payload.items),
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "request_ids": [],
            "created_at": now,
            "started_at": now,
            "finished_at": None,
            "updated_at": now,
        }
        with self.store.lock():
            self.store.batches[batch_id] = batch_record
        self.store.persist_batch(batch_record)

        success_count = 0
        failed_count = 0
        for item in payload.items:
            try:
                self._moderate_batch_item(batch_id, payload.tenant_id, payload.policy_id, item)
                success_count += 1
            except APIError:
                failed_count += 1

        with self.store.lock():
            batch = self.store.batches[batch_id]
            batch["processed_count"] = len(payload.items)
            batch["success_count"] = success_count
            batch["failed_count"] = failed_count
            batch["status"] = (
                BatchStatus.SUCCESS.value
                if failed_count == 0
                else BatchStatus.PARTIAL_SUCCESS.value
            )
            batch["finished_at"] = utcnow()
            batch["updated_at"] = batch["finished_at"]
        self.store.persist_batch(self.store.batches[batch_id])

        return BatchCreateData(
            batch_id=batch_id,
            status=self.store.batches[batch_id]["status"],
            total_count=len(payload.items),
            query_url=f"/api/v1/moderation/batches/{batch_id}",
        )

    def get_batch_status(self, batch_id: UUID) -> BatchStatusData:
        batch = self.store.batches.get(batch_id)
        if batch is None:
            raise APIError(status_code=404, code="not_found", message="Batch not found")
        return BatchStatusData(**{k: batch[k] for k in BatchStatusData.model_fields})

    def list_batch_items(
        self,
        batch_id: UUID,
        page: int,
        page_size: int,
        decision: str | None = None,
        risk_level: str | None = None,
    ) -> tuple[list[BatchItemResult], int]:
        batch = self.store.batches.get(batch_id)
        if batch is None:
            raise APIError(status_code=404, code="not_found", message="Batch not found")
        request_ids = batch.get("request_ids", [])
        items: list[BatchItemResult] = []
        for request_id in request_ids:
            result_id = self.store.result_by_request_id.get(request_id)
            if result_id is None:
                continue
            result = self.store.results[result_id]
            if decision and result["decision"] != decision.lower():
                continue
            if risk_level and result["risk_level"] != risk_level.lower():
                continue
            items.append(
                BatchItemResult(
                    request_id=request_id,
                    trace_id=result["trace_id"],
                    content_id=result["content_id"],
                    decision=display_decision(result["decision"]),
                    risk_level=display_risk_level(result["risk_level"]),
                    fallback_triggered=result["fallback_triggered"],
                    created_at=result["created_at"],
                )
            )
        total = len(items)
        start = max((page - 1) * page_size, 0)
        end = start + page_size
        return items[start:end], total

    def get_review_task_list_items(self) -> list[ReviewTaskListItem]:
        items: list[ReviewTaskListItem] = []
        for task in self.store.review_tasks.values():
            result = self.store.results[task["result_id"]]
            items.append(
                ReviewTaskListItem(
                    task_id=task["task_id"],
                    content_id=result["content_id"],
                    decision=display_decision(result["decision"]),
                    risk_level=display_risk_level(result["risk_level"]),
                    hit_rules=[hit["rule_id"] for hit in result["hit_rules"]],
                    status=task["status"],
                    created_at=task["created_at"],
                )
            )
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def get_review_task_detail(self, task_id: UUID) -> ReviewTaskDetail:
        task = self.store.review_tasks.get(task_id)
        if task is None:
            raise APIError(status_code=404, code="not_found", message="Review task not found")
        result = self.store.results[task["result_id"]]
        assignee = None
        if task.get("assignee_user_id"):
            user = self.store.users.get(task["assignee_user_id"])
            if user:
                assignee = {"user_id": user["user_id"], "display_name": user["display_name"]}
        first_entity_id = next((entity.get("entity_id") for entity in result["entities"] if entity.get("entity_id")), None)
        knowledge_card = self.store.knowledge_cards.get(first_entity_id) if first_entity_id else None
        feedback = [
            record
            for record in self.store.feedbacks.values()
            if record["task_id"] == task_id
        ]
        return ReviewTaskDetail(
            task_id=task["task_id"],
            status=task["status"],
            content_id=result["content_id"],
            content_text=result["content_text"],
            decision=display_decision(result["decision"]),
            risk_level=display_risk_level(result["risk_level"]),
            assignee=assignee,
            hit_rules=result["hit_rules"],
            entities=result["entities"],
            evidence_spans=result["evidence_spans"],
            ontology_facts=result["ontology_facts"],
            knowledge_card=knowledge_card,
            feedback=feedback,
            created_at=task["created_at"],
            completed_at=task["completed_at"],
        )

    def _moderate_batch_item(
        self,
        batch_id: UUID,
        tenant_code: str,
        policy_id: str | None,
        item: BatchItemRequest,
    ) -> None:
        _, request_id = self._moderate(
            ModerationSyncRequest(
                content_id=item.content_id,
                content_text=item.content_text,
                content_type=item.content_type,
                scenario=item.scenario,
                policy_id=policy_id,
                tenant_id=tenant_code,
                metadata=item.metadata,
            ),
            batch_id=batch_id,
        )
        with self.store.lock():
            batch = self.store.batches[batch_id]
            batch["request_ids"].append(request_id)
            batch_snapshot = self.store.snapshot(batch)
            result_id = self.store.result_by_request_id.get(request_id)
            result_snapshot = self.store.snapshot(self.store.results[result_id]) if result_id else None
            task_snapshot = (
                self.store.snapshot(self.store.review_tasks[self.store.review_task_by_result_id[result_id]])
                if result_id and result_id in self.store.review_task_by_result_id
                else None
            )
            request_snapshot = self.store.snapshot(self.store.requests[request_id])
        if result_snapshot is not None:
            self.store.persist_moderation_bundle(request_snapshot, result_snapshot, batch_snapshot, task_snapshot)

    def _resolve_tenant_id(self, tenant_identifier: str) -> UUID:
        tenant_id = self.store.tenant_code_index.get(tenant_identifier)
        if tenant_id is None:
            raise APIError(status_code=404, code="not_found", message="Tenant not found")
        return tenant_id

    def _default_client_id_for_tenant(self, tenant_id: UUID) -> UUID | None:
        for client in self.store.api_clients.values():
            if client["tenant_id"] == tenant_id and client["status"] == "active":
                return client["client_id"]
        return None

    def _resolve_policy_version(self, policy_code: str | None) -> dict[str, Any] | None:
        if not policy_code:
            return next(iter(self.store.policy_versions.values()), None)
        policy_id = self.store.policy_code_index.get(policy_code)
        if policy_id is None:
            raise APIError(status_code=404, code="not_found", message="Policy not found")
        versions = [
            version for version in self.store.policy_versions.values() if version["policy_id"] == policy_id
        ]
        published = [version for version in versions if version["status"] == "published"]
        return sorted(published, key=lambda item: item["version_no"], reverse=True)[0] if published else None

    def _published_kb_version(self) -> dict[str, Any]:
        published = [kb for kb in self.store.kb_versions.values() if kb["status"] == "published"]
        if not published:
            raise APIError(status_code=503, code="ontology_unavailable", message="No published KB version")
        return sorted(published, key=lambda item: item["published_at"], reverse=True)[0]

    def _find_span(self, text: str, needle: str, start_from: int = 0) -> tuple[int, int] | None:
        index = text.find(needle, start_from)
        if index < 0:
            return None
        return index, index + len(needle)

    def _entity(self, text: str, needle: str, standard_name: str, entity_type: str, entity_id: str | None = None) -> ExtractedEntity:
        span = self._find_span(text, needle)
        if span is None:
            raise ValueError(f"Entity {needle!r} not found in text")
        return ExtractedEntity(
            text=needle,
            standard_name=standard_name,
            type=entity_type,
            start=span[0],
            end=span[1],
            confidence=0.91,
            entity_id=entity_id,
        )

    def _evidence(self, text: str, snippet: str, rule_id: str, entity_id: str | None = None) -> EvidenceSpan:
        span = self._find_span(text, snippet)
        if span is None:
            span = self._find_span(text, snippet.replace("，", ""))
        if span is None:
            span = (0, min(len(text), len(snippet)))
        return EvidenceSpan(
            text=text[span[0]:span[1]],
            start=span[0],
            end=span[1],
            rule_id=rule_id,
            entity_id=entity_id,
        )

    def _evaluate_text(self, text: str, scenario: Scenario) -> list[ModerationMatch]:
        matches: list[ModerationMatch] = []
        if "附子" in text and scenario in {Scenario.TEA_DRINK, Scenario.FOOD_THERAPY, Scenario.GENERAL_HEALTH, Scenario.WEIGHT_LOSS}:
            entity = self._entity(text, "附子", "附子", "material", "mat_001")
            matches.append(
                ModerationMatch(
                    rule_code="R001",
                    rule_name="药食同源/原料身份校验",
                    decision=Decision.BLOCK,
                    risk_level=RiskLevel.HIGH,
                    reason="高风险药材附子不应直接用于食疗/茶饮场景。",
                    entities=[entity],
                    evidence_spans=[self._evidence(text, "附子", "R001", "mat_001")],
                    ontology_facts=[
                        OntologyFact(
                            subject="附子",
                            relation="PROHIBITED_IN_CONTEXT",
                            object=scenario.value,
                            kb_version="kb-2026-05-29-01",
                        )
                    ],
                )
            )
        if "甘草" in text and "海藻" in text:
            entity_a = self._entity(text, "甘草", "甘草", "material", "mat_002")
            entity_b = self._entity(text, "海藻", "海藻", "material", "mat_003")
            matches.append(
                ModerationMatch(
                    rule_code="R002",
                    rule_name="配伍禁忌校验",
                    decision=Decision.REVIEW,
                    risk_level=RiskLevel.HIGH,
                    reason="甘草与海藻存在配伍禁忌关系。",
                    entities=[entity_a, entity_b],
                    evidence_spans=[self._evidence(text, "甘草", "R002", "mat_002"), self._evidence(text, "海藻", "R002", "mat_003")],
                    ontology_facts=[
                        OntologyFact(
                            subject="甘草",
                            relation="CONTRAINDICATED_WITH",
                            object="海藻",
                            kb_version="kb-2026-05-29-01",
                        )
                    ],
                )
            )
        effect_terms = ["降血糖", "治疗", "根治", "治结节"]
        if any(term in text for term in effect_terms) and scenario in {Scenario.TEA_DRINK, Scenario.FOOD_THERAPY, Scenario.GENERAL_HEALTH}:
            hit_term = next(term for term in effect_terms if term in text)
            standard_name = "降低血糖/糖尿病相关功效" if hit_term == "降血糖" else f"{hit_term}相关疾病功效"
            effect_entity_id = "eff_001" if hit_term == "降血糖" else None
            matches.append(
                ModerationMatch(
                    rule_code="R003",
                    rule_name="功效宣称越界",
                    decision=Decision.BLOCK,
                    risk_level=RiskLevel.HIGH,
                    reason="普通食疗/茶饮内容宣称治疗疾病。",
                    entities=[self._entity(text, hit_term, standard_name, "effect", effect_entity_id)],
                    evidence_spans=[self._evidence(text, hit_term, "R003", effect_entity_id)],
                    ontology_facts=[
                        OntologyFact(
                            subject=scenario.value,
                            relation="ASSOCIATED_WITH_DISEASE",
                            object=standard_name,
                            kb_version="kb-2026-05-29-01",
                        )
                    ],
                )
            )
        populations = [term for term in ("孕妇", "儿童", "老人") if term in text]
        long_term_terms = [term for term in ("长期", "每天", "大剂量", "长期喝") if term in text]
        if populations and long_term_terms:
            population_term = populations[0]
            matches.append(
                ModerationMatch(
                    rule_code="R004",
                    rule_name="特殊人群长期服用风险",
                    decision=Decision.REVIEW,
                    risk_level=RiskLevel.MEDIUM,
                    reason="涉及特殊人群与长期服用表述。",
                    entities=[self._entity(text, population_term, population_term, "population", "pop_001" if population_term == "孕妇" else None)],
                    evidence_spans=[self._evidence(text, population_term, "R004")],
                    ontology_facts=[
                        OntologyFact(
                            subject="内容场景",
                            relation="NOT_FOR_POPULATION",
                            object=population_term,
                            kb_version="kb-2026-05-29-01",
                        )
                    ],
                )
            )
        return matches

    def _summarize(
        self, matches: list[ModerationMatch]
    ) -> tuple[Decision, RiskLevel, RecommendedAction, str]:
        if not matches:
            return (
                Decision.PASS,
                RiskLevel.LOW,
                RecommendedAction.ALLOW,
                "未命中高风险规则或显著知识风险，建议通过。",
            )
        decision = Decision.REVIEW
        risk_level = RiskLevel.MEDIUM
        if any(match.decision == Decision.BLOCK for match in matches):
            decision = Decision.BLOCK
        if any(match.risk_level == RiskLevel.HIGH for match in matches):
            risk_level = RiskLevel.HIGH
        if any(match.risk_level == RiskLevel.CRITICAL for match in matches):
            risk_level = RiskLevel.CRITICAL

        if decision == Decision.BLOCK:
            recommended_action = RecommendedAction.BLOCK_OR_MANUAL_CONFIRM
            explanation = "内容命中高风险规则，且存在明确知识或规则证据，建议拦截或人工二次确认。"
        else:
            recommended_action = RecommendedAction.EXPERT_REVIEW
            explanation = "内容存在不确定或中高风险知识信号，建议进入人工复核。"
        return decision, risk_level, recommended_action, explanation

    def _confidence(self, matches: list[ModerationMatch]) -> float:
        if not matches:
            return 0.96
        if any(match.decision == Decision.BLOCK for match in matches):
            return 0.92
        return 0.86

    def _unique_entities(self, matches: list[ModerationMatch]) -> list[ExtractedEntity]:
        seen: set[tuple[str, int, int]] = set()
        result: list[ExtractedEntity] = []
        for match in matches:
            for entity in match.entities:
                key = (entity.text, entity.start, entity.end)
                if key not in seen:
                    seen.add(key)
                    result.append(entity)
        return result

    def _unique_evidence(self, matches: list[ModerationMatch]) -> list[EvidenceSpan]:
        seen: set[tuple[str, int, int, str | None]] = set()
        result: list[EvidenceSpan] = []
        for match in matches:
            for evidence in match.evidence_spans:
                key = (evidence.text, evidence.start, evidence.end, evidence.rule_id)
                if key not in seen:
                    seen.add(key)
                    result.append(evidence)
        return result

    def _unique_facts(self, matches: list[ModerationMatch]) -> list[OntologyFact]:
        seen: set[tuple[str, str, str]] = set()
        result: list[OntologyFact] = []
        for match in matches:
            for fact in match.ontology_facts:
                key = (fact.subject, fact.relation, fact.object)
                if key not in seen:
                    seen.add(key)
                    result.append(fact)
        return result

    def _create_review_task(self, result_record: dict[str, Any], tenant_id: UUID, now: Any) -> dict[str, Any] | None:
        if result_record["result_id"] in self.store.review_task_by_result_id:
            return None
        assignee_user_id = next(
            (
                membership["user_id"]
                for membership in self.store.memberships.values()
                if membership["tenant_id"] == tenant_id and membership["role_code"] == "reviewer"
            ),
            None,
        )
        task_id = uuid4()
        self.store.review_tasks[task_id] = {
            "task_id": task_id,
            "result_id": result_record["result_id"],
            "tenant_id": tenant_id,
            "assignee_user_id": assignee_user_id,
            "status": ReviewTaskStatus.PENDING.value,
            "queue_name": "default",
            "sla_due_at": now + timedelta(hours=4),
            "final_decision": None,
            "final_action": None,
            "overwrite_system_decision": False,
            "resolution_reason": None,
            "resolution_note": None,
            "claimed_at": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self.store.review_task_by_result_id[result_record["result_id"]] = task_id
        return self.store.review_tasks[task_id]

    def _as_scenario(self, scenario: Scenario | str) -> Scenario:
        if isinstance(scenario, Scenario):
            return scenario
        try:
            return Scenario(str(scenario))
        except ValueError as exc:
            raise APIError(status_code=400, code="invalid_request", message="Invalid scenario") from exc

    def _enum_value(self, value: Any) -> str:
        return value.value if hasattr(value, "value") else str(value)
