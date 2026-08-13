"""Pure bounded-loop state and fingerprint checks."""

from __future__ import annotations

import hashlib
import time

from agentic_text2sql.contracts.correction import StopReason
from agentic_text2sql.contracts.validation import ValidationReport


def error_fingerprint(report: ValidationReport) -> str:
    value = "|".join(
        [report.error_class.value if report.error_class else "NONE", *sorted(report.signals)]
    )
    return hashlib.sha256(value.encode()).hexdigest()


class LoopController:
    def __init__(
        self,
        *,
        max_repairs: int = 1,
        max_llm_calls: int = 1,
        deadline: float | None = None,
        min_remaining_seconds: float = 1.0,
    ) -> None:
        if not 0 <= max_repairs <= 2:
            raise ValueError("max_repairs must be between 0 and 2")
        if max_llm_calls < 0:
            raise ValueError("max_llm_calls cannot be negative")
        self.max_repairs = max_repairs
        self.max_llm_calls = max_llm_calls
        self.deadline = deadline
        self.min_remaining_seconds = min_remaining_seconds

    def before_repair(self, *, repairs: int, llm_calls: int) -> StopReason | None:
        if repairs >= self.max_repairs:
            return StopReason.MAX_REPAIRS
        if llm_calls >= self.max_llm_calls:
            return StopReason.CALL_BUDGET
        deadline_exhausted = (
            self.deadline is not None
            and time.monotonic() + self.min_remaining_seconds >= self.deadline
        )
        if deadline_exhausted:
            return StopReason.DEADLINE
        return None
