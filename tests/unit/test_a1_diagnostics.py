from agentic_text2sql.contracts.assessment import (
    A1Trace,
    CheckOutcome,
    ClauseAssessment,
    ClauseFinding,
)
from agentic_text2sql.contracts.sql import DirectRunResult, DirectStatus
from agentic_text2sql_eval.a1_diagnostics import ReviewedA1Label, diagnose_a1
from agentic_text2sql_eval.inference_runner import SmokePrediction


def prediction(case_id: str, *, contradiction: bool) -> SmokePrediction:
    findings = (
        ()
        if not contradiction
        else (
            ClauseFinding(
                code="EXPLICIT_RANK_DIRECTION",
                clause="ORDER BY",
                outcome=CheckOutcome.CONTRADICTION,
                message="wrong direction",
            ),
        )
    )
    trace = A1Trace(
        critic_mode="shadow",
        generation_format="json",
        max_requests=3,
        actual_generation_requests=1,
        draft_checks=ClauseAssessment(findings=findings),
    )
    return SmokePrediction(
        case_id=case_id,
        result=DirectRunResult(
            run_id=case_id,
            question="Show scores",
            status=DirectStatus.SUCCEEDED,
            route_reason="query",
            prompt_versions={},
            assessment=trace.model_dump(mode="json"),
        ),
    )


def test_diagnostics_does_not_treat_unreviewed_execution_as_accuracy() -> None:
    report = diagnose_a1([prediction("a", contradiction=False)], [])
    assert report["unreviewed"] == 1
    assert report["final_accuracy"] is None
    assert report["pool_oracle_accuracy"] is None
    assert report["detector"]["precision"] is None


def test_diagnostics_measures_false_positives_on_valid_drafts() -> None:
    predictions = [
        prediction("bad", contradiction=True),
        prediction("valid", contradiction=True),
        prediction("missed", contradiction=False),
        prediction("clean", contradiction=False),
    ]
    labels = [
        ReviewedA1Label(
            case_id=case,
            review_status="REVIEWED",
            reviewer="independent-review",
            semantic_error=case in {"bad", "missed"},
            contradictory_codes=("EXPLICIT_RANK_DIRECTION",) if case == "bad" else (),
        )
        for case in ("bad", "valid", "missed", "clean")
    ]
    report = diagnose_a1(predictions, labels)
    assert report["detector"] == {
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "tn": 1,
        "precision": 0.5,
        "recall": 0.5,
        "false_positive_rate": 0.5,
    }
    assert report["final_accuracy"] is None
