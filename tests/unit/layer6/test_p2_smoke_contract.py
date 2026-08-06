from pathlib import Path

from agentic_text2sql.contracts.sql import DirectStatus
from agentic_text2sql_eval.inference_runner import load_smoke_cases


def test_p2_smoke_set_has_twenty_unique_reviewable_cases() -> None:
    root = Path(__file__).resolve().parents[3]
    cases = load_smoke_cases(root / "evals/configs/olist-smoke-20.jsonl")
    assert len(cases) == 20
    assert len({case.id for case in cases}) == 20
    assert sum(case.expected_status is DirectStatus.SUCCEEDED for case in cases) == 18
    assert any(case.expected_status is DirectStatus.CLARIFY for case in cases)
    assert any(case.expected_status is DirectStatus.WRITE_BLOCKED for case in cases)
    assert all(case.gold_sql for case in cases if case.expected_status is DirectStatus.SUCCEEDED)
