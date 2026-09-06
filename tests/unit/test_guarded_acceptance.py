from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    unsafe_reason,
)


def test_resource_guard_fails_closed_for_each_threshold() -> None:
    safe = ResourceSample(15, 0, 3000, 60, 50, 100, 600)
    limits = ResourceLimits()
    assert unsafe_reason(safe, limits) is None
    assert "available RAM" in str(unsafe_reason(ResourceSample(13, 0, 3000, 60, 50, 100), limits))
    assert "swap" in str(unsafe_reason(ResourceSample(15, 0.25, 3000, 60, 50, 100), limits))
    assert "VRAM" in str(unsafe_reason(ResourceSample(15, 0, 12000, 60, 50, 100), limits))
    assert "temperature" in str(unsafe_reason(ResourceSample(15, 0, 3000, 68, 50, 100), limits))
    assert "power" in str(unsafe_reason(ResourceSample(15, 0, 3000, 60, 70, 100), limits))
    assert "clock" in str(unsafe_reason(ResourceSample(15, 0, 3000, 60, 50, 100, 1800), limits))


def test_profiles_bound_parallelism_and_long_run_unloads() -> None:
    interactive = PROFILES[ProfileName.INTERACTIVE]
    acceptance = PROFILES[ProfileName.ACCEPTANCE]
    assert interactive.ollama_environment()["OLLAMA_NUM_PARALLEL"] == "1"
    assert interactive.max_loaded_models == 2
    assert interactive.ollama_num_gpu == 6
    assert acceptance.batch_size == 1
    assert acceptance.keep_alive == "0"
    assert acceptance.cooldown_seconds == 20
    ultrasafe = PROFILES[ProfileName.OLIST_PAPER1]
    assert ultrasafe.ollama_num_gpu == 1
    assert ultrasafe.batch_size == 1
    assert ultrasafe.cooldown_seconds == 60
    assert ultrasafe.limits.maximum_gpu_memory_mib == 4096
    assert ultrasafe.limits.maximum_gpu_temperature_c == 65
    assert ultrasafe.limits.maximum_gpu_power_w == 78
    assert ultrasafe.limits.maximum_gpu_graphics_clock_mhz == 650
