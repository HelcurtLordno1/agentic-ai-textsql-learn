from __future__ import annotations

import json
from dataclasses import replace
from io import StringIO

from agentic_text2sql.gpu_monitor import GpuMonitor
from agentic_text2sql.hardware import PROFILES, ProfileName, parse_gpu_sample, unsafe_reason


def test_cpu300_only_tightens_old_cpu_clock_limit() -> None:
    old = PROFILES[ProfileName.QWEN_CPU_600_STABLE].model_dump()
    new = PROFILES[ProfileName.QWEN_CPU_300_STABLE].model_dump()
    for key in ("name", "description"):
        old.pop(key)
        new.pop(key)
    assert old["limits"].pop("maximum_gpu_clock_mhz") == 600
    assert new["limits"].pop("maximum_gpu_clock_mhz") == 300
    assert old == new
    assert new["ollama_num_gpu"] == 0


def test_raw_journal_keeps_instantaneous_spike_and_safe_followup() -> None:
    sensor = GpuMonitor()
    journal = StringIO()
    sensor.journal = journal
    sensor._accept("1000, 46, 58.42, 74.56, 100, 300")
    sensor._accept("1000, 46, 17, 18, 0, 300")
    rows = [json.loads(line) for line in journal.getvalue().splitlines()]
    assert rows[0]["power_average_w"] == 58.42
    assert rows[0]["power_instant_w"] == 74.56
    assert rows[1]["power_instant_w"] == 18
    assert rows[0]["received_at_ms"] <= rows[1]["received_at_ms"]
    assert sensor.pending is not None
    assert (
        unsafe_reason(
            replace(sensor.pending, available_ram_gib=20),
            PROFILES[ProfileName.QWEN_CPU_300_STABLE].limits,
        )
        == "GPU power 74.6 W"
    )


def test_either_power_channel_must_still_trip_guard() -> None:
    limits = PROFILES[ProfileName.QWEN_CPU_300_STABLE].limits
    for average, instant in [(74.56, 58.42), (58.42, 74.56)]:
        sample = replace(
            parse_gpu_sample(f"1000, 46, {average}, {instant}, 100, 300"), available_ram_gib=20
        )
        assert unsafe_reason(sample, limits) == "GPU power 74.6 W"
