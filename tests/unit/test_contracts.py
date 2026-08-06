import pytest
from pydantic import ValidationError

from agentic_text2sql.contracts.planning import LogicalPlan
from agentic_text2sql.contracts.sql import SqlCandidate


def test_logical_plan_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LogicalPlan(
            question_language="vi",
            task_type="ranking",
            metrics=["revenue"],
            dimensions=["category"],
            unexpected="nope",
        )


def test_sql_candidate_enforces_confidence_range() -> None:
    with pytest.raises(ValidationError):
        SqlCandidate(sql="SELECT 1", confidence=1.1)
