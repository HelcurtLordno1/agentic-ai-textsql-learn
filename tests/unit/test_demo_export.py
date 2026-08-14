import pytest

from scripts.export_demo_artifacts import sanitize_report


def test_demo_export_excludes_details_and_requires_complete_report() -> None:
    summary = sanitize_report(
        {
            "evaluation_id": "spider-dev-1034-p6-v1",
            "release_status": "complete",
            "case_count": 1034,
            "result_accuracy": 0.5,
            "details": [{"generated_sql": "SELECT secret"}],
        }
    )
    assert "details" not in summary
    with pytest.raises(ValueError, match="complete"):
        sanitize_report({"release_status": "checkpointed", "case_count": 10})
