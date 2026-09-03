import pytest

from agentic_text2sql_eval.question_reliability import (
    ReliabilityJudgment,
    ReliabilityLabel,
    evaluate_reliability,
)


def test_reliability_metrics_keep_accuracy_and_coverage_failures_visible() -> None:
    report = evaluate_reliability(
        [
            ReliabilityJudgment(
                case_id="a1",
                expected=ReliabilityLabel.ANSWER,
                predicted=ReliabilityLabel.ANSWER,
            ),
            ReliabilityJudgment(
                case_id="a2",
                expected=ReliabilityLabel.ANSWER,
                predicted=ReliabilityLabel.CLARIFY,
            ),
            ReliabilityJudgment(
                case_id="c1",
                expected=ReliabilityLabel.CLARIFY,
                predicted=ReliabilityLabel.CLARIFY,
                clarification_resolved=True,
            ),
            ReliabilityJudgment(
                case_id="c2",
                expected=ReliabilityLabel.CLARIFY,
                predicted=ReliabilityLabel.ANSWER,
                clarification_resolved=False,
            ),
            ReliabilityJudgment(
                case_id="u1",
                expected=ReliabilityLabel.CANNOT_ANSWER,
                predicted=ReliabilityLabel.CANNOT_ANSWER,
            ),
        ]
    )

    assert report.case_count == 5
    assert report.ambiguity_recall == 0.5
    assert report.answerable_false_refusal == 0.5
    assert report.clarification_success == 0.5
    assert report.confusion["ANSWER"]["CLARIFY"] == 1


def test_reliability_metrics_reject_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="unique"):
        evaluate_reliability(
            [
                ReliabilityJudgment(
                    case_id="same",
                    expected=ReliabilityLabel.ANSWER,
                    predicted=ReliabilityLabel.ANSWER,
                ),
                ReliabilityJudgment(
                    case_id="same",
                    expected=ReliabilityLabel.CLARIFY,
                    predicted=ReliabilityLabel.CLARIFY,
                ),
            ]
        )
