from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    unsafe_reason,
)


def test_resource_guard_fails_closed_for_each_threshold() -> None:
    safe = ResourceSample(15, 0, 2000, 60, 50, 100)
    limits = ResourceLimits()
    assert unsafe_reason(safe, limits) is None
    assert "available RAM" in str(unsafe_reason(ResourceSample(13, 0, 2000, 60, 50, 100), limits))
    assert "swap" in str(unsafe_reason(ResourceSample(15, 0.25, 2000, 60, 50, 100), limits))
    assert "VRAM" in str(unsafe_reason(ResourceSample(15, 0, 6144, 60, 50, 100), limits))
    assert "temperature" in str(unsafe_reason(ResourceSample(15, 0, 2000, 68, 50, 100), limits))
    assert "power" in str(unsafe_reason(ResourceSample(15, 0, 2000, 60, 70, 100), limits))
    assert "graphics clock" in str(
        unsafe_reason(ResourceSample(15, 0, 2000, 60, 50, 100, 1800), limits)
    )


def test_r1_reliability_profile_is_ultrasafe() -> None:
    profile = PROFILES[ProfileName.R1_RELIABILITY]

    assert profile.batch_size == 1
    assert profile.ollama_num_gpu == 4
    assert profile.max_loaded_models == 1
    assert profile.cooldown_seconds >= 45
    assert profile.limits.minimum_available_ram_gib >= 14
    assert profile.limits.maximum_gpu_memory_mib <= 6144
    assert profile.limits.maximum_gpu_temperature_c <= 68
    assert profile.limits.maximum_gpu_power_w <= 70


def test_olist_paper1_profile_keeps_qwen14b_gpu_offload_minimal() -> None:
    profile = PROFILES[ProfileName.OLIST_PAPER1]

    assert profile.batch_size == 1
    assert profile.ollama_num_gpu == 1
    assert profile.max_loaded_models == 1
    assert profile.cooldown_seconds >= 60
    assert profile.limits.maximum_gpu_memory_mib <= 4096
    assert profile.limits.maximum_gpu_temperature_c <= 65
    assert profile.limits.maximum_gpu_power_w <= 78
    assert profile.limits.maximum_gpu_graphics_clock_mhz <= 650


def test_profiles_bound_parallelism_and_long_run_unloads() -> None:
    interactive = PROFILES[ProfileName.INTERACTIVE]
    benchmark = PROFILES[ProfileName.BENCHMARK]
    acceptance = PROFILES[ProfileName.ACCEPTANCE]
    assert interactive.ollama_environment()["OLLAMA_NUM_PARALLEL"] == "1"
    assert interactive.max_loaded_models == 1
    assert interactive.ollama_num_gpu == 6
    assert benchmark.ollama_num_gpu == 6
    assert benchmark.batch_size == 1
    assert benchmark.max_loaded_models == 1
    assert benchmark.keep_alive == "0"
    assert benchmark.cooldown_seconds >= 60
    assert benchmark.limits.minimum_available_ram_gib >= 14
    assert benchmark.limits.maximum_swap_used_gib <= 0.25
    assert benchmark.limits.maximum_gpu_memory_mib <= 6144
    assert benchmark.limits.maximum_gpu_temperature_c <= 68
    assert benchmark.limits.maximum_gpu_power_w <= 70
    assert acceptance.batch_size == 1
    assert acceptance.keep_alive == "0"
    assert acceptance.cooldown_seconds == 20


def test_all_non_exception_profiles_use_current_conservative_limits() -> None:
    for name, profile in PROFILES.items():
        if name == ProfileName.OLIST_PAPER1:
            continue
        assert profile.limits.minimum_available_ram_gib >= 14
        assert profile.limits.maximum_swap_used_gib <= 0.25
        assert profile.limits.maximum_gpu_memory_mib <= 6144
        assert profile.limits.maximum_gpu_temperature_c <= 68
        assert profile.limits.maximum_gpu_power_w <= 70
