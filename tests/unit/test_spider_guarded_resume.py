from __future__ import annotations

from pathlib import Path

import pytest

from agentic_text2sql.hardware import PROFILES, ProfileName, ResourceSample, unsafe_reason
from agentic_text2sql.settings import Settings
from scripts.launch_r2_spider_tmux import build_window_shells
from scripts.run_benchmark import run_configuration, verify_resume_provenance
from scripts.run_guarded_spider import maximum_observation


def test_spider_profile_keeps_conservative_breakers() -> None:
    profile = PROFILES[ProfileName.SPIDER_PAPER2]
    assert profile.ollama_num_gpu == 1
    assert profile.batch_size == 1
    assert profile.cooldown_seconds >= 60
    assert profile.max_loaded_models == 1
    assert profile.limits.maximum_gpu_power_w <= 70
    assert profile.limits.maximum_gpu_memory_mib < 6144
    assert profile.limits.maximum_gpu_graphics_clock_mhz <= 601
    hot = ResourceSample(15, 0, 1000, 50, 20, 20, 750)
    assert unsafe_reason(hot, profile.limits) is not None


def test_resume_rejects_any_changed_identity() -> None:
    configuration = run_configuration(
        Settings(), correction_enabled=True, profile=ProfileName.SPIDER_PAPER2.value
    )
    expected = {
        "git_commit": "a" * 40,
        "experiment_id": "spider-r2-test",
        "manifest_sha256": "b" * 64,
        "index_pointer_sha256": {"tiny": "c" * 64},
        "run_config": configuration,
        "database_runtime": {},
    }
    kwargs = {
        "revision": {"git_commit": "a" * 40},
        "evaluation_id": "spider-r2-test",
        "manifest_sha256": "b" * 64,
        "index_pointer_sha256": {"tiny": "c" * 64},
        "run_config": configuration,
    }
    verify_resume_provenance(expected, **kwargs)
    for changed in (
        "git_commit",
        "experiment_id",
        "manifest_sha256",
        "index_pointer_sha256",
        "run_config",
    ):
        payload = {**expected, changed: "different"}
        with pytest.raises(SystemExit, match=f"SPIDER_RESUME_MISMATCH: {changed}"):
            verify_resume_provenance(payload, **kwargs)


def test_peak_merges_worst_resource_values() -> None:
    first = ResourceSample(20, 0.1, 1000, 50, 30, 20, 300)
    second = ResourceSample(15, 0.2, 1200, 52, 40, 50, 600)
    assert maximum_observation(first, second) == second


def test_tmux_launcher_runs_one_case_pilot_then_resume_with_two_guards(tmp_path: Path) -> None:
    server, benchmark = build_window_shells(
        tmp_path,
        evaluation_id="spider-r2-test",
        session="spider-test",
        models_dir=tmp_path / "models with spaces",
    )
    assert "serve_ollama_guarded.py" in server
    assert "--stop-record" in server and "spider-paper2-ultrasafe" in server
    assert "models with spaces" in server
    assert benchmark.count("run_guarded_spider.py") == 2
    assert "--phase pilot --max-batches 1" in benchmark
    assert "--phase inference" in benchmark
    assert "trap cleanup EXIT" in benchmark
    assert "--batch-size 1 --cooldown-seconds 60 --sample-seconds 0.5" in benchmark
