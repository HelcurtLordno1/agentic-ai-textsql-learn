"""Typed laptop runtime profiles and fail-closed resource observations."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GIB = 1024**3


class ProfileName(StrEnum):
    INTERACTIVE = "interactive-balanced"
    ACCEPTANCE = "acceptance-safe"
    CPU_FALLBACK = "cpu-fallback"
    OLIST_PAPER1 = "olist-paper1-ultrasafe"
    OLIST_PAPER2_A4500 = "olist-paper2-a4500-safe"
    SPIDER_PAPER2 = "spider-paper2-ultrasafe"


class ResourceLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    minimum_available_ram_gib: float = Field(default=14, gt=0)
    maximum_swap_used_gib: float = Field(default=0.25, gt=0)
    maximum_gpu_memory_mib: int = Field(default=6144, gt=0)
    maximum_gpu_temperature_c: int = Field(default=68, gt=0)
    maximum_gpu_power_w: float = Field(default=70, gt=0)
    maximum_gpu_graphics_clock_mhz: int = Field(default=1800, gt=0)


class HardwareProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: ProfileName
    description: str
    ollama_num_gpu: int = Field(ge=0)
    cpu_cores: int = Field(ge=1)
    context_length: int = Field(default=4096, ge=1024)
    max_loaded_models: int = Field(ge=1, le=2)
    keep_alive: str
    flash_attention: bool
    kv_cache_type: str
    batch_size: int = Field(ge=1, le=3)
    cooldown_seconds: int = Field(ge=0)
    retrieval_mode: Literal["bm25", "dense", "hybrid"] = "hybrid"
    max_output_tokens: int = Field(default=768, ge=128, le=2048)
    request_timeout_seconds: int = Field(default=240, ge=30, le=900)
    run_deadline_seconds: int = Field(default=120, ge=30, le=300)
    limits: ResourceLimits = ResourceLimits()

    def ollama_environment(self) -> dict[str, str]:
        return {
            "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_LOADED_MODELS": str(self.max_loaded_models),
            "OLLAMA_MAX_QUEUE": "2",
            "OLLAMA_KEEP_ALIVE": self.keep_alive,
            "OLLAMA_CONTEXT_LENGTH": str(self.context_length),
            "OLLAMA_FLASH_ATTENTION": "1" if self.flash_attention else "0",
            "OLLAMA_KV_CACHE_TYPE": self.kv_cache_type,
            "TEXT2SQL_OLLAMA_NUM_GPU": str(self.ollama_num_gpu),
            "TEXT2SQL_OLLAMA_MAX_OUTPUT_TOKENS": str(self.max_output_tokens),
            "TEXT2SQL_REQUEST_TIMEOUT_SECONDS": str(self.request_timeout_seconds),
            "TEXT2SQL_RUN_DEADLINE_SECONDS": str(self.run_deadline_seconds),
            "TEXT2SQL_RETRIEVAL_MODE": self.retrieval_mode,
        }


PROFILES = {
    ProfileName.INTERACTIVE: HardwareProfile(
        name=ProfileName.INTERACTIVE,
        description=(
            "Keep Qwen and BGE resident to avoid model thrash while bounding compute offload."
        ),
        ollama_num_gpu=6,
        cpu_cores=12,
        max_loaded_models=2,
        keep_alive="5m",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=0,
    ),
    ProfileName.ACCEPTANCE: HardwareProfile(
        name=ProfileName.ACCEPTANCE,
        description="One checkpointed case, explicit unload, and cooldown for long benchmarks.",
        ollama_num_gpu=6,
        cpu_cores=12,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=20,
    ),
    ProfileName.CPU_FALLBACK: HardwareProfile(
        name=ProfileName.CPU_FALLBACK,
        description="Emergency no-GPU mode; slow but avoids discrete-GPU compute pressure.",
        ollama_num_gpu=0,
        cpu_cores=8,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=False,
        kv_cache_type="f16",
        batch_size=1,
        cooldown_seconds=30,
    ),
    ProfileName.OLIST_PAPER1: HardwareProfile(
        name=ProfileName.OLIST_PAPER1,
        description="Qwen3-14B Olist evaluation with minimal GPU offload and hard breakers.",
        ollama_num_gpu=1,
        cpu_cores=6,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
        limits=ResourceLimits(
            minimum_available_ram_gib=14,
            maximum_swap_used_gib=0.25,
            maximum_gpu_memory_mib=4096,
            maximum_gpu_temperature_c=65,
            maximum_gpu_power_w=78,
            maximum_gpu_graphics_clock_mhz=650,
        ),
    ),
    ProfileName.OLIST_PAPER2_A4500: HardwareProfile(
        name=ProfileName.OLIST_PAPER2_A4500,
        description=("Qwen3-14B Olist DIN-SQL evaluation on RTX A4500 with one-case residency."),
        ollama_num_gpu=6,
        cpu_cores=10,
        max_loaded_models=1,
        keep_alive="5m",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
        retrieval_mode="bm25",
        max_output_tokens=512,
        request_timeout_seconds=240,
        run_deadline_seconds=180,
        limits=ResourceLimits(
            minimum_available_ram_gib=14,
            maximum_swap_used_gib=0.25,
            maximum_gpu_memory_mib=4096,
            maximum_gpu_temperature_c=65,
            maximum_gpu_power_w=70,
            maximum_gpu_graphics_clock_mhz=650,
        ),
    ),
    ProfileName.SPIDER_PAPER2: HardwareProfile(
        name=ProfileName.SPIDER_PAPER2,
        description="One-case Spider R2 pilot and resume with conservative laptop breakers.",
        ollama_num_gpu=1,
        cpu_cores=6,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
        request_timeout_seconds=240,
        run_deadline_seconds=180,
        limits=ResourceLimits(
            minimum_available_ram_gib=14,
            maximum_swap_used_gib=0.25,
            maximum_gpu_memory_mib=4096,
            maximum_gpu_temperature_c=65,
            maximum_gpu_power_w=70,
            maximum_gpu_graphics_clock_mhz=901,
        ),
    ),
}


@dataclass(frozen=True)
class ResourceSample:
    available_ram_gib: float
    swap_used_gib: float
    gpu_memory_mib: int
    gpu_temperature_c: int
    gpu_power_w: float
    gpu_utilization_pct: int
    gpu_graphics_clock_mhz: int = 0


def sample_resources() -> ResourceSample:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", maxsplit=1)
        values[key] = int(value.split()[0]) * 1024
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,temperature.gpu,power.draw,utilization.gpu,clocks.current.graphics",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=5,
    ).strip()
    memory, temperature, power, utilization, graphics_clock = [
        item.strip() for item in output.split(",")
    ]
    return ResourceSample(
        available_ram_gib=values["MemAvailable"] / GIB,
        swap_used_gib=(values["SwapTotal"] - values["SwapFree"]) / GIB,
        gpu_memory_mib=int(memory),
        gpu_temperature_c=int(temperature),
        gpu_power_w=float(power),
        gpu_utilization_pct=int(utilization),
        gpu_graphics_clock_mhz=int(graphics_clock),
    )


def unsafe_reason(sample: ResourceSample, limits: ResourceLimits) -> str | None:
    checks = (
        (
            sample.available_ram_gib < limits.minimum_available_ram_gib,
            f"available RAM {sample.available_ram_gib:.1f} GiB",
        ),
        (
            sample.swap_used_gib >= limits.maximum_swap_used_gib,
            f"swap {sample.swap_used_gib:.1f} GiB",
        ),
        (
            sample.gpu_memory_mib >= limits.maximum_gpu_memory_mib,
            f"VRAM {sample.gpu_memory_mib} MiB",
        ),
        (
            sample.gpu_temperature_c >= limits.maximum_gpu_temperature_c,
            f"GPU temperature {sample.gpu_temperature_c} C",
        ),
        (sample.gpu_power_w >= limits.maximum_gpu_power_w, f"GPU power {sample.gpu_power_w:.1f} W"),
        (
            sample.gpu_graphics_clock_mhz >= limits.maximum_gpu_graphics_clock_mhz,
            f"GPU graphics clock {sample.gpu_graphics_clock_mhz} MHz",
        ),
    )
    return next((message for failed, message in checks if failed), None)
