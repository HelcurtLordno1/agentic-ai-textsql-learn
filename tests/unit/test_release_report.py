import json
from pathlib import Path

import pytest

from agentic_text2sql_eval.release_report import build_release_report


def write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_release_report_keeps_scores_separate_and_requires_complete_inputs(
    tmp_path: Path,
) -> None:
    olist = write(tmp_path / "olist.json", {"case_count": 60, "result_accuracy": 0.9})
    spider = write(
        tmp_path / "spider.json",
        {
            "case_count": 200,
            "release_status": "complete",
            "result_accuracy": 0.5,
            "manifest": {"benchmark_profile": "laptop-stratified"},
        },
    )
    retrieval = write(tmp_path / "retrieval.json", {"evaluation_id": "retrieval-modes"})
    correction = write(tmp_path / "correction.json", {"evaluation_id": "correction-off-on"})
    report = build_release_report(
        olist_report_path=olist,
        spider_report_path=spider,
        retrieval_ablation_path=retrieval,
        correction_ablation_path=correction,
    )
    assert "result_accuracy" not in report
    assert report["olist"]["result_accuracy"] == 0.9
    assert report["spider"]["result_accuracy"] == 0.5
    assert set(report["ablations"]) == {"retrieval", "correction"}
    with pytest.raises(ValueError, match="Olist-60"):
        build_release_report(
            olist_report_path=write(tmp_path / "bad.json", {"case_count": 59}),
            spider_report_path=spider,
            retrieval_ablation_path=retrieval,
            correction_ablation_path=correction,
        )
