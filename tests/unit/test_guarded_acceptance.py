from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    unsafe_reason,
)


def test_resource_guard_fails_closed_for_each_threshold() -> None:
    safe = ResourceSample(15, 0, 7000, 60, 50, 100)
    limits = ResourceLimits()
    assert unsafe_reason(safe, limits) is None
    assert "available RAM" in str(unsafe_reason(ResourceSample(9, 0, 7000, 60, 50, 100), limits))
    assert "swap" in str(unsafe_reason(ResourceSample(15, 1, 7000, 60, 50, 100), limits))
    assert "VRAM" in str(unsafe_reason(ResourceSample(15, 0, 12000, 60, 50, 100), limits))
    assert "temperature" in str(unsafe_reason(ResourceSample(15, 0, 7000, 76, 50, 100), limits))
    assert "power" in str(unsafe_reason(ResourceSample(15, 0, 7000, 60, 105, 100), limits))


def test_profiles_bound_parallelism_and_long_run_unloads() -> None:
    interactive = PROFILES[ProfileName.INTERACTIVE]
    acceptance = PROFILES[ProfileName.ACCEPTANCE]
    assert interactive.ollama_environment()["OLLAMA_NUM_PARALLEL"] == "1"
    assert interactive.max_loaded_models == 2
    assert interactive.ollama_num_gpu == 8
    assert acceptance.batch_size == 1
    assert acceptance.keep_alive == "0"
    assert acceptance.cooldown_seconds == 20
