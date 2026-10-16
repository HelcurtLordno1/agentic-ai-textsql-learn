"""One invocation budget shared by roles and provider-level format retries."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from agentic_text2sql.exceptions import Text2SQLError


class BudgetExceededError(Text2SQLError):
    """The next request cannot fit the invocation budget."""


@dataclass
class RequestBudget:
    max_requests: int = 3
    deadline_seconds: float = 120
    started: float = field(default_factory=time.monotonic)
    attempts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 1 <= self.max_requests <= 3 or self.deadline_seconds <= 0:
            raise ValueError("A1 requires 1..3 requests and a positive deadline")

    @property
    def remaining_seconds(self) -> float:
        return max(0, self.deadline_seconds - (time.monotonic() - self.started))

    def check(self) -> None:
        if self.remaining_seconds <= 0:
            raise BudgetExceededError("Invocation deadline exhausted")

    def consume(self, stage: str) -> None:
        self.check()
        if len(self.attempts) >= self.max_requests:
            raise BudgetExceededError("Shared generation request budget exhausted")
        self.attempts.append(stage)

    def can_request(self, minimum_seconds: float = 1.0) -> bool:
        return len(self.attempts) < self.max_requests and self.remaining_seconds >= minimum_seconds


@dataclass(frozen=True)
class RequestScope:
    budget: RequestBudget
    stage: str
    output_tokens: int


ACTIVE_REQUEST: ContextVar[RequestScope | None] = ContextVar("text2sql_request", default=None)


@contextmanager
def request_scope(budget: RequestBudget, stage: str, output_tokens: int) -> Iterator[None]:
    token = ACTIVE_REQUEST.set(RequestScope(budget, stage, output_tokens))
    try:
        yield
    finally:
        ACTIVE_REQUEST.reset(token)
