from __future__ import annotations

from collections import Counter

from ..schemas import ReportOverview, ReviewQualityReport, RuleHitReportItem
from ..store import InMemoryStore


class ReportService:
    def __init__(self, store: InMemoryStore) -> None:
        self.store = store

    def overview(self) -> ReportOverview:
        results = list(self.store.results.values())
        total_requests = len(results)
        decision_distribution = Counter(result["decision"] for result in results)
        total_tasks = len(self.store.review_tasks)
        completed_tasks = sum(1 for task in self.store.review_tasks.values() if task["status"] == "completed")
        overwrite_count = sum(1 for task in self.store.review_tasks.values() if task["overwrite_system_decision"])
        fallback_count = sum(1 for result in results if result["fallback_triggered"])
        p95 = max((result["latency_ms"] for result in results), default=0)
        return ReportOverview(
            total_requests=total_requests,
            decision_distribution=dict(decision_distribution),
            review_completion_rate=(completed_tasks / total_tasks if total_tasks else 1.0),
            overwrite_rate=(overwrite_count / total_tasks if total_tasks else 0.0),
            api_p95_ms=p95,
            fallback_rate=(fallback_count / total_requests if total_requests else 0.0),
        )

    def rule_hits(self) -> list[RuleHitReportItem]:
        counter: dict[str, dict[str, int | str]] = {}
        for result in self.store.results.values():
            for hit in result["hit_rules"]:
                record = counter.setdefault(
                    hit["rule_id"],
                    {
                        "rule_code": hit["rule_id"],
                        "rule_name": hit["rule_name"],
                        "hit_count": 0,
                        "block_count": 0,
                        "review_count": 0,
                    },
                )
                record["hit_count"] += 1
                if hit["decision"] == "Block":
                    record["block_count"] += 1
                if hit["decision"] == "Review":
                    record["review_count"] += 1
        return [RuleHitReportItem(**item) for item in counter.values()]

    def review_quality(self) -> ReviewQualityReport:
        total_review_tasks = len(self.store.review_tasks)
        completed_review_tasks = sum(1 for task in self.store.review_tasks.values() if task["status"] == "completed")
        feedback_counts = Counter(feedback["feedback_type"] for feedback in self.store.feedbacks.values())
        overwrite_count = sum(1 for task in self.store.review_tasks.values() if task["overwrite_system_decision"])
        return ReviewQualityReport(
            total_review_tasks=total_review_tasks,
            completed_review_tasks=completed_review_tasks,
            feedback_counts=dict(feedback_counts),
            overwrite_count=overwrite_count,
            overwrite_rate=(overwrite_count / total_review_tasks if total_review_tasks else 0.0),
        )
