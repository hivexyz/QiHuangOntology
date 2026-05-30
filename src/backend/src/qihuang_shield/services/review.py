from __future__ import annotations

from uuid import UUID, uuid4

from ..exceptions import APIError
from ..schemas import FeedbackCreateRequest, ReviewTaskDetail, ReviewTaskListItem, SubmitReviewTaskRequest
from ..store import InMemoryStore
from ..utils import enum_value, paginate, utcnow
from .moderation import ModerationService


class ReviewService:
    def __init__(self, store: InMemoryStore, moderation_service: ModerationService) -> None:
        self.store = store
        self.moderation_service = moderation_service

    def list_tasks(
        self,
        page: int,
        page_size: int,
        status: str | None = None,
        risk_level: str | None = None,
        rule_code: str | None = None,
        scenario: str | None = None,
        assignee_user_id: UUID | None = None,
    ) -> tuple[list[ReviewTaskListItem], int, int, int]:
        items = self.moderation_service.get_review_task_list_items()
        filtered: list[ReviewTaskListItem] = []
        for item in items:
            if status and item.status != status:
                continue
            if risk_level and item.risk_level.lower() != risk_level.lower():
                continue
            if rule_code and rule_code not in item.hit_rules:
                continue
            if scenario:
                task = self.store.review_tasks[item.task_id]
                result = self.store.results[task["result_id"]]
                if result["scenario"] != scenario:
                    continue
            if assignee_user_id is not None:
                task = self.store.review_tasks[item.task_id]
                if task.get("assignee_user_id") != assignee_user_id:
                    continue
            filtered.append(item)
        total = len(filtered)
        page, page_size, total_pages = paginate(total, page, page_size)
        start = (page - 1) * page_size
        return filtered[start:start + page_size], total, page, total_pages

    def get_task(self, task_id: UUID) -> ReviewTaskDetail:
        return self.moderation_service.get_review_task_detail(task_id)

    def claim_task(self, task_id: UUID, operator_user_id: UUID) -> ReviewTaskDetail:
        task = self.store.review_tasks.get(task_id)
        if task is None:
            raise APIError(status_code=404, code="not_found", message="Review task not found")
        now = utcnow()
        with self.store.lock():
            if task["status"] in {"completed", "closed"}:
                raise APIError(status_code=409, code="conflict", message="Task is already closed")
            task["assignee_user_id"] = operator_user_id
            task["status"] = "claimed"
            task["claimed_at"] = now
            task["updated_at"] = now
        self.store.persist_review_task(task)
        return self.get_task(task_id)

    def submit_task(self, task_id: UUID, payload: SubmitReviewTaskRequest) -> ReviewTaskDetail:
        task = self.store.review_tasks.get(task_id)
        if task is None:
            raise APIError(status_code=404, code="not_found", message="Review task not found")
        if task["status"] == "completed":
            return self.get_task(task_id)
        now = utcnow()
        with self.store.lock():
            task["assignee_user_id"] = payload.operator_user_id
            task["status"] = "completed"
            task["final_decision"] = enum_value(payload.final_decision)
            task["final_action"] = enum_value(payload.final_action)
            task["overwrite_system_decision"] = payload.overwrite_system_decision
            task["resolution_reason"] = payload.resolution_reason
            task["resolution_note"] = payload.resolution_note
            task["completed_at"] = now
            task["updated_at"] = now
            audit_id = uuid4()
            self.store.audit_logs[audit_id] = {
                "audit_id": audit_id,
                "tenant_id": task["tenant_id"],
                "actor_type": "user",
                "actor_user_id": payload.operator_user_id,
                "actor_client_id": None,
                "action": "review_task_submit",
                "resource_type": "review_task",
                "resource_id": str(task_id),
                "change_summary": payload.model_dump(),
                "trace_id": self.store.results[task["result_id"]]["trace_id"],
                "ip_address": None,
                "user_agent": None,
                "created_at": now,
            }
            audit_log = self.store.audit_logs[audit_id]
        self.store.persist_review_task(task)
        self.store.persist_audit_log(audit_log)
        return self.get_task(task_id)

    def add_feedback(self, task_id: UUID, payload: FeedbackCreateRequest, operator_user_id: UUID) -> dict:
        task = self.store.review_tasks.get(task_id)
        if task is None:
            raise APIError(status_code=404, code="not_found", message="Review task not found")
        now = utcnow()
        feedback_id = uuid4()
        feedback = {
            "feedback_id": feedback_id,
            "task_id": task_id,
            "result_id": task["result_id"],
            "tenant_id": task["tenant_id"],
            "feedback_type": enum_value(payload.feedback_type),
            "target_rule_id": str(payload.target_rule_id) if payload.target_rule_id else None,
            "target_entity_ref_id": payload.target_entity_ref_id,
            "comment": payload.comment,
            "labels": payload.labels,
            "created_by": operator_user_id,
            "created_at": now,
        }
        with self.store.lock():
            self.store.feedbacks[feedback_id] = feedback
        self.store.persist_feedback(feedback)
        return feedback
