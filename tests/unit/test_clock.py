from __future__ import annotations

import pytest

from agentic_text2sql import clock
from agentic_text2sql.workflow.budgets import RequestBudget


def test_budget_uses_raw_elapsed_despite_wall_and_slewed_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = 10.0
    monkeypatch.setattr(clock.time, "clock_gettime", lambda which: raw)
    monkeypatch.setattr(clock.time, "time", lambda: -999999.0)
    monkeypatch.setattr(clock.time, "monotonic", lambda: 999999.0)
    budget = RequestBudget(deadline_seconds=180)
    raw += 60
    assert budget.remaining_seconds == 120
    raw += 121
    assert budget.remaining_seconds == 0


def test_cooldown_never_finishes_early_when_os_sleep_clock_slews(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = 0.0

    def sleep(seconds: float) -> None:
        nonlocal raw
        raw += max(seconds * 0.9, 0.000001)

    monkeypatch.setattr(clock, "monotonic_seconds", lambda: raw)
    monkeypatch.setattr(clock.time, "sleep", sleep)
    clock.sleep_seconds(60)
    assert 60 <= raw < 60.001
    with pytest.raises(ValueError):
        clock.sleep_seconds(-1)
