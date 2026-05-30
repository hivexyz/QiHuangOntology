from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class APIError(Exception):
    status_code: int
    code: str
    message: str
    retryable: bool = False
    details: list[dict[str, str | None]] = field(default_factory=list)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
