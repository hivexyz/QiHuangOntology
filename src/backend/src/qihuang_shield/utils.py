from __future__ import annotations

from datetime import UTC, datetime
from math import ceil
from typing import Any
from uuid import uuid4

from .enums import Decision, RiskLevel


DECISION_DISPLAY = {
    Decision.PASS: "Pass",
    Decision.REVIEW: "Review",
    Decision.BLOCK: "Block",
}

RISK_LEVEL_DISPLAY = {
    RiskLevel.LOW: "Low",
    RiskLevel.MEDIUM: "Medium",
    RiskLevel.HIGH: "High",
    RiskLevel.CRITICAL: "Critical",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_trace_id() -> str:
    return f"trc_{uuid4().hex}"


def display_decision(decision: Decision | str) -> str:
    try:
        return DECISION_DISPLAY[Decision(decision)]
    except (KeyError, ValueError):
        return str(decision)


def display_risk_level(risk_level: RiskLevel | str) -> str:
    try:
        return RISK_LEVEL_DISPLAY[RiskLevel(risk_level)]
    except (KeyError, ValueError):
        return str(risk_level)


def enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def paginate(total: int, page: int, page_size: int) -> tuple[int, int, int]:
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    total_pages = max(1, ceil(total / page_size)) if total else 1
    return page, page_size, total_pages
