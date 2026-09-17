import sqlite3
from pathlib import Path

from agentic_text2sql.contracts.catalog import CatalogSnapshot
from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    unsafe_reason,
)
from scripts.run_guarded_acceptance import cool_down_if_incomplete, stage_runtime_inputs


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
    a4500 = PROFILES[ProfileName.OLIST_PAPER2_A4500]
    assert a4500.ollama_num_gpu == 6
    assert a4500.cpu_cores == 10
    assert a4500.max_loaded_models == 1
    assert a4500.keep_alive == "5m"
    assert a4500.batch_size == 1
    assert a4500.cooldown_seconds == 60
    assert a4500.retrieval_mode == "bm25"
    assert a4500.max_output_tokens == 512
    assert a4500.request_timeout_seconds == 240
    assert a4500.run_deadline_seconds == 180
    assert a4500.limits.maximum_gpu_memory_mib == 4096
    assert a4500.limits.maximum_gpu_temperature_c == 65
    assert a4500.limits.maximum_gpu_power_w == 70
    assert a4500.limits.maximum_gpu_graphics_clock_mhz == 650
    environment = a4500.ollama_environment()
    assert environment["TEXT2SQL_OLLAMA_NUM_GPU"] == "6"
    assert environment["TEXT2SQL_RETRIEVAL_MODE"] == "bm25"
    assert environment["TEXT2SQL_REQUEST_TIMEOUT_SECONDS"] == "240"


def test_pilot_cools_after_an_incomplete_checkpoint() -> None:
    waits: list[float] = []

    cool_down_if_incomplete(1, 45, 60, sleep=waits.append)
    cool_down_if_incomplete(45, 45, 60, sleep=waits.append)

    assert waits == [60]


def test_runtime_inputs_are_staged_once_with_verified_catalog(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE orders(order_id TEXT PRIMARY KEY)")

    database, catalog_path, digest = stage_runtime_inputs(source, tmp_path / "staged")

    assert database.read_bytes() == source.read_bytes()
    assert len(digest) == 64
    catalog = CatalogSnapshot.model_validate_json(catalog_path.read_text(encoding="utf-8"))
    assert catalog.db_id == "olist"
    assert [table.name for table in catalog.tables] == ["orders"]
