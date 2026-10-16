from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_text2sql_eval.suite_control import prediction_prefix, require_complete_report


@pytest.mark.parametrize("ids", [["b"], ["a", "a"], ["a", "b", "c"]])
def test_checkpoint_rejects_out_of_order_duplicate_or_overrun(
    tmp_path: Path,
    ids: list[str],
) -> None:
    path = tmp_path / "predictions.jsonl"
    path.write_text("\n".join(json.dumps({"case_id": value}) for value in ids))
    with pytest.raises(ValueError, match="prefix"):
        prediction_prefix(path, ["a", "b"])


def test_completion_requires_complete_report_not_only_a_full_checkpoint(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"case_count": 2, "details": [{"id": "a"}]}))
    with pytest.raises(ValueError, match="partial"):
        require_complete_report(report, ["a", "b"])
    report.write_text(json.dumps({"case_count": 2, "details": [{"id": "a"}, {"id": "b"}]}))
    require_complete_report(report, ["a", "b"])
