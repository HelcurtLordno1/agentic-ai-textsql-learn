import pytest

from agentic_text2sql_eval.shadow_certification import certify_shadow_proofs


def row(
    case_id: str,
    *,
    incumbent: bool,
    challenger: bool,
    partition: str = "dev",
    proof_kind: str = "aggregate:max",
) -> dict[str, object]:
    return {
        "id": case_id,
        "partition": partition,
        "challenger_available": True,
        "proof_kind": proof_kind,
        "incumbent_correct": incumbent,
        "challenger_correct": challenger,
    }


def test_certification_requires_support_gain_and_zero_regressions() -> None:
    report = {
        "evaluation_id": "shadow-v1",
        "candidate_shadow": {
            "details": [
                row("a", incumbent=False, challenger=True),
                row("b", incumbent=True, challenger=True),
                row("c", incumbent=True, challenger=True, proof_kind="aggregate:avg"),
                row("d", incumbent=True, challenger=True, proof_kind="aggregate:avg"),
                row("e", incumbent=True, challenger=True, proof_kind="frequency_ranking"),
                row("locked", incumbent=True, challenger=False, partition="holdout"),
            ]
        },
    }

    result = certify_shadow_proofs(report)

    assert result["certified_proof_kinds"] == [
        "aggregate:avg",
        "aggregate:max",
        "frequency_ranking",
    ]
    assert result["proof_family"]["count"] == 5
    assert result["metrics"]["aggregate:max"]["count"] == 2
    assert result["metrics"]["aggregate:max"]["regressions"] == 0


def test_certification_rejects_one_regression_or_insufficient_support() -> None:
    regression = {
        "candidate_shadow": {
            "details": [
                row("a", incumbent=False, challenger=True),
                row("b", incumbent=True, challenger=True),
                row("c", incumbent=True, challenger=True, proof_kind="aggregate:avg"),
                row("d", incumbent=True, challenger=True, proof_kind="aggregate:avg"),
                row("e", incumbent=True, challenger=False, proof_kind="frequency_ranking"),
            ]
        }
    }
    insufficient = {"candidate_shadow": {"details": [row("a", incumbent=False, challenger=True)]}}

    assert certify_shadow_proofs(regression)["certified_proof_kinds"] == []
    assert certify_shadow_proofs(insufficient)["certified_proof_kinds"] == []


def test_certification_rejects_invalid_thresholds() -> None:
    report = {"candidate_shadow": {"details": []}}
    with pytest.raises(ValueError):
        certify_shadow_proofs(report, minimum_cases=0)
    with pytest.raises(ValueError):
        certify_shadow_proofs(report, minimum_accuracy=0)
    with pytest.raises(ValueError):
        certify_shadow_proofs(report, minimum_proof_kinds=0)
