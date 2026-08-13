from scripts.run_guarded_acceptance import Sample, unsafe_reason


def test_resource_guard_fails_closed_for_each_threshold() -> None:
    safe = Sample(15, 0, 7000, 60, 50, 100)
    thresholds = {
        "minimum_available_ram_gib": 10,
        "maximum_swap_used_gib": 1,
        "maximum_gpu_memory_mib": 11776,
        "maximum_gpu_temperature_c": 76,
        "maximum_gpu_power_w": 95,
    }
    assert unsafe_reason(safe, **thresholds) is None
    assert "available RAM" in str(unsafe_reason(Sample(9, 0, 7000, 60, 50, 100), **thresholds))
    assert "swap" in str(unsafe_reason(Sample(15, 1, 7000, 60, 50, 100), **thresholds))
    assert "VRAM" in str(unsafe_reason(Sample(15, 0, 12000, 60, 50, 100), **thresholds))
    assert "temperature" in str(unsafe_reason(Sample(15, 0, 7000, 76, 50, 100), **thresholds))
    assert "power" in str(unsafe_reason(Sample(15, 0, 7000, 60, 95, 100), **thresholds))
