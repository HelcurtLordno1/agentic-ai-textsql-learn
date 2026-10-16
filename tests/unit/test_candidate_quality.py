from agentic_text2sql_eval.candidate_quality import summarize_candidates


def test_final_repairs_are_not_counted_as_first_pass_and_unscored_pools_stay_unscored() -> None:
    repaired = {
        "result_correct": True,
        "a1_candidates": {
            "first_pass_correct": False,
            "pool_oracle_correct": True,
            "repair_source": "deterministic",
            "generation_requests": 1,
        },
    }
    unscored = {
        "result_correct": False,
        "a1_candidates": {
            "first_pass_correct": None,
            "pool_oracle_correct": None,
            "repair_source": "model",
            "generation_requests": 2,
        },
    }
    metrics = summarize_candidates([repaired, unscored])
    assert metrics["first_pass_scored"] == metrics["pool_scored"] == 1
    assert metrics["first_pass_accuracy"] == 0
    assert metrics["pool_oracle_accuracy"] == 1
    assert metrics["gain"] == 1 and metrics["loss"] == 0
    assert metrics["cpu_repairs"] == 1 and metrics["generation_requests"] == 3
