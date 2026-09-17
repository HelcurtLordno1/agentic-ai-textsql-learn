import hashlib
from pathlib import Path

import pytest

from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql_eval.inference_runner import SmokePrediction
from agentic_text2sql_eval.olist_acceptance import OlistAcceptanceCase
from scripts.run_r2_olist_recovery import (
    audit_source_seed,
    merge_predictions,
    resolve_source_artifacts,
)


def _case(case_id: str) -> OlistAcceptanceCase:
    return OlistAcceptanceCase(
        id=case_id,
        partition="dev",
        language="en",
        question=f"question {case_id}",
        difficulty="easy",
        required_concepts=(),
        gold_sql=f"SELECT '{case_id}'",
        reviewed=True,
    )


def _line(case_id: str, value: str) -> str:
    return SmokePrediction(
        case_id=case_id,
        result=DirectRunResult(
            run_id=f"run-{case_id}",
            question=f"question {case_id}",
            status=DirectStatus.SUCCEEDED,
            route_reason="query",
            prompt_versions={},
            result_rows=[[value]],
        ),
    ).model_dump_json()


def test_sparse_merge_preserves_success_bytes_and_replaces_only_recovery_ids(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    recovery = tmp_path / "recovery.jsonl"
    destination = tmp_path / "combined.jsonl"
    one = _line("case_001", "preserved")
    source.write_text(f"{one}\n{_line('case_002', 'old failure')}\n", encoding="utf-8")
    recovery.write_text(
        f"{_line('case_002', 'fixed')}\n{_line('case_003', 'new')}\n",
        encoding="utf-8",
    )

    merged = merge_predictions(
        cases=[_case("case_001"), _case("case_002"), _case("case_003")],
        source_predictions=source,
        recovery_predictions=recovery,
        preserved_hashes={"case_001": hashlib.sha256(one.encode()).hexdigest()},
        destination=destination,
    )

    assert [prediction.case_id for prediction in merged] == [
        "case_001",
        "case_002",
        "case_003",
    ]
    assert destination.read_text(encoding="utf-8").splitlines()[0] == one
    assert merged[1].result.result_rows == [["fixed"]]


def test_sparse_merge_refuses_changed_preserved_seed(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    recovery = tmp_path / "recovery.jsonl"
    source.write_text(f"{_line('case_001', 'tampered')}\n", encoding="utf-8")
    recovery.write_text(f"{_line('case_002', 'new')}\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="PRESERVED_SEED_CHANGED"):
        merge_predictions(
            cases=[_case("case_001"), _case("case_002")],
            source_predictions=source,
            recovery_predictions=recovery,
            preserved_hashes={"case_001": "0" * 64},
            destination=tmp_path / "combined.jsonl",
        )


def test_seed_audit_binds_cached_correctness_to_prediction_outputs(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    one = _line("case_001", "correct")
    two = _line("case_002", "wrong")
    source.write_text(f"{one}\n{two}\n", encoding="utf-8")
    report = tmp_path / "source-progress.json"
    report.write_text(
        """
        {
          "details": [
            {"id":"case_001","status":"SUCCEEDED","actual_rows":[["correct"]],
             "generated_sql":null,"result_correct":true},
            {"id":"case_002","status":"SUCCEEDED","actual_rows":[["wrong"]],
             "generated_sql":null,"result_correct":false}
          ]
        }
        """,
        encoding="utf-8",
    )

    preserved, recovery, hashes = audit_source_seed(
        source_predictions=source,
        cases=[_case("case_001"), _case("case_002"), _case("case_003")],
        database=tmp_path / "unused.sqlite",
        audit_report=tmp_path / "audit.json",
        evaluation_id="recovery",
        source_report=report,
    )

    assert preserved == ("case_001",)
    assert recovery == ("case_002", "case_003")
    assert hashes == {"case_001": hashlib.sha256(one.encode()).hexdigest()}


def test_seed_audit_accepts_complete_manifest_and_selects_only_failures(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    one = _line("case_001", "correct")
    two = _line("case_002", "wrong")
    source.write_text(f"{one}\n{two}\n", encoding="utf-8")
    report = tmp_path / "source-report.json"
    report.write_text(
        """
        {
          "details": [
            {"id":"case_001","status":"SUCCEEDED","actual_rows":[["correct"]],
             "generated_sql":null,"result_correct":true},
            {"id":"case_002","status":"SUCCEEDED","actual_rows":[["wrong"]],
             "generated_sql":null,"result_correct":false}
          ]
        }
        """,
        encoding="utf-8",
    )

    preserved, recovery, _ = audit_source_seed(
        source_predictions=source,
        cases=[_case("case_001"), _case("case_002")],
        database=tmp_path / "unused.sqlite",
        audit_report=tmp_path / "audit.json",
        evaluation_id="recovery",
        source_report=report,
    )

    assert preserved == ("case_001",)
    assert recovery == ("case_002",)


def test_source_artifacts_inherit_certification_for_complete_recovery(tmp_path: Path) -> None:
    predictions = tmp_path / "predictions"
    reports = tmp_path / "reports"
    predictions.mkdir()
    reports.mkdir()
    combined_predictions = predictions / "recovery-v1-combined-olist60.jsonl"
    combined_report = reports / "recovery-v1-combined-olist60.json"
    provenance = reports / "recovery-v1.provenance.json"
    certification = reports / "proof-v4.certification.json"
    combined_predictions.write_text("{}\n", encoding="utf-8")
    combined_report.write_text("{}\n", encoding="utf-8")
    provenance.write_text('{"source_evaluation_id":"proof-v4"}\n', encoding="utf-8")
    certification.write_text("{}\n", encoding="utf-8")

    assert resolve_source_artifacts(tmp_path, "recovery-v1") == (
        combined_predictions,
        certification,
        combined_report,
    )
