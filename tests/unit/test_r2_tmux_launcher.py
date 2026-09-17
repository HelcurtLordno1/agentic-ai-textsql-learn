from pathlib import Path

from scripts.launch_r2_olist_tmux import build_window_shells


def test_tmux_windows_use_both_guards_and_cleanup_server(tmp_path: Path) -> None:
    server, benchmark = build_window_shells(
        tmp_path,
        evaluation_id="r2-test-v2",
        session="olist-r2-test",
        models_dir=tmp_path / "models with spaces",
        skip_check=True,
    )

    assert "serve_ollama_guarded.py" in server
    assert "olist-paper1-ultrasafe" in server
    assert "run_r2_olist_research.py" in benchmark
    assert "run_olist_acceptance.py" not in benchmark
    assert "--skip-check" in benchmark
    assert "trap cleanup EXIT" in benchmark
    assert "tmux send-keys -t olist-r2-test:server C-c" in benchmark
    assert "R2_BENCHMARK_EXIT=$status" in benchmark
    assert "2>&1" in benchmark
    assert "models with spaces" in server


def test_tmux_recovery_uses_sparse_runner_without_weakening_guards(tmp_path: Path) -> None:
    server, benchmark = build_window_shells(
        tmp_path,
        evaluation_id="r2-recovery-v1",
        session="olist-r2-recovery-v1",
        models_dir=None,
        skip_check=False,
        recovery_source_evaluation_id="r2-proof-complete-v4",
    )

    assert "serve_ollama_guarded.py" in server
    assert "run_r2_olist_recovery.py" in benchmark
    assert "--source-evaluation-id r2-proof-complete-v4" in benchmark
    assert "run_r2_olist_research.py" not in benchmark
    assert "trap cleanup EXIT" in benchmark
