"""Typed laptop runtime profiles and fail-closed resource observations."""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

GIB = 1024**3


class ProfileName(StrEnum):
    INTERACTIVE = "interactive-balanced"
    ACCEPTANCE = "acceptance-safe"
    CPU_FALLBACK = "cpu-fallback"
    CLOCK_CAPPED = "clock-capped-safe"
    QWEN_FULL_GPU = "qwen14b-16gb-clock-capped"
    QWEN_V4_600_B16 = "qwen14b-v4-600-b16"
    QWEN_CPU_300_STABLE = "qwen14b-cpu300-stable"
    QWEN_CPU_600_STABLE = "qwen14b-cpu600-stable"
    QWEN_GPU300_F16_B16 = "qwen14b-gpu300-f16-b16"


class ResourceLimits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    minimum_available_ram_gib: float = Field(default=14, gt=0)
    maximum_swap_used_gib: float = Field(default=0.25, gt=0)
    maximum_gpu_memory_mib: int = Field(default=6144, gt=0)
    maximum_gpu_temperature_c: int = Field(default=68, gt=0)
    maximum_gpu_power_w: float = Field(default=70, gt=0)
    maximum_gpu_clock_mhz: int | None = Field(default=None, gt=0)


class HardwareProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: ProfileName
    description: str
    ollama_num_gpu: int = Field(ge=0)
    cpu_cores: int = Field(ge=1)
    prompt_batch_tokens: int = Field(default=64, ge=1, le=256)
    context_length: int = Field(default=4096, ge=1024)
    run_deadline_seconds: int = Field(default=120, ge=30, le=900)
    request_timeout_seconds: int = Field(default=120, ge=1, le=300)
    max_loaded_models: int = Field(ge=1, le=1)
    keep_alive: str
    flash_attention: bool
    kv_cache_type: str
    batch_size: int = Field(ge=1, le=1)
    cooldown_seconds: int = Field(ge=0)
    limits: ResourceLimits = ResourceLimits()

    @model_validator(mode="after")
    def bound_cpu_deadline(self) -> HardwareProfile:
        approved_gpu = self.name is ProfileName.QWEN_GPU300_F16_B16
        if approved_gpu and (
            self.ollama_num_gpu != 41
            or self.cpu_cores != 8
            or self.prompt_batch_tokens != 16
            or self.context_length != 4096
            or self.run_deadline_seconds != 900
            or self.request_timeout_seconds != 300
            or self.flash_attention
            or self.kv_cache_type != "f16"
            or self.keep_alive != "0"
            or self.cooldown_seconds < 60
            or self.limits.maximum_gpu_clock_mhz != 300
            or self.limits.minimum_available_ram_gib < 8
            or self.limits.maximum_swap_used_gib > 0.25
            or self.limits.maximum_gpu_memory_mib > 14336
            or self.limits.maximum_gpu_temperature_c > 68
            or self.limits.maximum_gpu_power_w > 70
        ):
            raise ValueError("GPU300 requires its complete approved bounded execution envelope")
        if self.run_deadline_seconds > 180 and self.ollama_num_gpu != 0 and not approved_gpu:
            raise ValueError("Deadlines above 180 seconds require explicit CPU-only offload")
        return self

    def ollama_environment(self) -> dict[str, str]:
        environment = {
            "OLLAMA_NUM_PARALLEL": "1",
            "OLLAMA_MAX_LOADED_MODELS": str(self.max_loaded_models),
            "OLLAMA_MAX_QUEUE": "2",
            "OLLAMA_KEEP_ALIVE": self.keep_alive,
            "OLLAMA_CONTEXT_LENGTH": str(self.context_length),
            "OLLAMA_FLASH_ATTENTION": "1" if self.flash_attention else "0",
            "OLLAMA_KV_CACHE_TYPE": self.kv_cache_type,
            "TEXT2SQL_OLLAMA_NUM_GPU": str(self.ollama_num_gpu),
            "TEXT2SQL_RUN_DEADLINE_SECONDS": str(self.run_deadline_seconds),
            "TEXT2SQL_REQUEST_TIMEOUT_SECONDS": str(self.request_timeout_seconds),
            "TEXT2SQL_OLLAMA_NUM_THREAD": str(self.cpu_cores),
            "TEXT2SQL_OLLAMA_NUM_BATCH": str(self.prompt_batch_tokens),
        }
        if self.name is ProfileName.QWEN_GPU300_F16_B16:
            environment["TEXT2SQL_GPU_EXECUTION_PROFILE"] = self.name.value
        return environment


PROFILES = {
    ProfileName.QWEN_GPU300_F16_B16: HardwareProfile(
        name=ProfileName.QWEN_GPU300_F16_B16,
        description="User-approved GPU41 at300MHz; f16/noFA and unchanged900/300s budgets.",
        ollama_num_gpu=41,
        cpu_cores=8,
        prompt_batch_tokens=16,
        run_deadline_seconds=900,
        request_timeout_seconds=300,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=False,
        kv_cache_type="f16",
        batch_size=1,
        cooldown_seconds=60,
        limits=ResourceLimits(
            minimum_available_ram_gib=8,
            maximum_gpu_memory_mib=14336,
            maximum_gpu_temperature_c=68,
            maximum_gpu_power_w=70,
            maximum_gpu_clock_mhz=300,
        ),
    ),
    ProfileName.QWEN_CPU_300_STABLE: HardwareProfile(
        name=ProfileName.QWEN_CPU_300_STABLE,
        description="CPU-only Qwen14B recovery; retain the user's 300 MHz graphics cap.",
        ollama_num_gpu=0,
        cpu_cores=8,
        prompt_batch_tokens=64,
        run_deadline_seconds=900,
        request_timeout_seconds=300,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=False,
        kv_cache_type="f16",
        batch_size=1,
        cooldown_seconds=60,
        limits=ResourceLimits(
            minimum_available_ram_gib=8,
            maximum_gpu_memory_mib=14336,
            maximum_gpu_temperature_c=68,
            maximum_gpu_power_w=70,
            maximum_gpu_clock_mhz=300,
        ),
    ),
    ProfileName.QWEN_CPU_600_STABLE: HardwareProfile(
        name=ProfileName.QWEN_CPU_600_STABLE,
        description="CPU-only Qwen14B recovery; retain the user's 600 MHz graphics cap.",
        ollama_num_gpu=0,
        cpu_cores=8,
        prompt_batch_tokens=64,
        run_deadline_seconds=900,
        request_timeout_seconds=300,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=False,
        kv_cache_type="f16",
        batch_size=1,
        cooldown_seconds=60,
        limits=ResourceLimits(
            minimum_available_ram_gib=8,
            maximum_gpu_memory_mib=14336,
            maximum_gpu_temperature_c=68,
            maximum_gpu_power_w=70,
            maximum_gpu_clock_mhz=600,
        ),
    ),
    ProfileName.QWEN_V4_600_B16: HardwareProfile(
        name=ProfileName.QWEN_V4_600_B16,
        description="Fresh full-GPU V4 calibration, 600 MHz cap and prompt batch 16.",
        ollama_num_gpu=41,
        cpu_cores=8,
        prompt_batch_tokens=16,
        run_deadline_seconds=180,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
        limits=ResourceLimits(
            minimum_available_ram_gib=8,
            maximum_gpu_memory_mib=14336,
            maximum_gpu_temperature_c=68,
            maximum_gpu_power_w=70,
            maximum_gpu_clock_mhz=600,
        ),
    ),
    ProfileName.QWEN_FULL_GPU: HardwareProfile(
        name=ProfileName.QWEN_FULL_GPU,
        description="User-authorized 16 GiB GPU / 32 GiB host, full offload and 450 MHz cap.",
        ollama_num_gpu=41,  # Installed Qwen3-14B has 40 transformer blocks + output.
        cpu_cores=8,
        run_deadline_seconds=180,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
        limits=ResourceLimits(
            minimum_available_ram_gib=8,
            maximum_gpu_memory_mib=14336,
            maximum_gpu_temperature_c=68,
            maximum_gpu_power_w=70,
            maximum_gpu_clock_mhz=450,
        ),
    ),
    ProfileName.CLOCK_CAPPED: HardwareProfile(
        name=ProfileName.CLOCK_CAPPED,
        description="800 MHz cap verification, host RAM monitoring, and conservative pilot/run.",
        ollama_num_gpu=20,
        cpu_cores=8,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
        limits=ResourceLimits(
            maximum_gpu_temperature_c=65,
            maximum_gpu_power_w=65,
            maximum_gpu_clock_mhz=800,
        ),
    ),
    ProfileName.INTERACTIVE: HardwareProfile(
        name=ProfileName.INTERACTIVE,
        description=(
            "Sequential local requests with conservative offload and explicit model unload."
        ),
        ollama_num_gpu=1,
        cpu_cores=12,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
    ),
    ProfileName.ACCEPTANCE: HardwareProfile(
        name=ProfileName.ACCEPTANCE,
        description="One checkpointed case, explicit unload, and cooldown for long benchmarks.",
        ollama_num_gpu=1,
        cpu_cores=12,
        max_loaded_models=1,
        keep_alive="0",
        flash_attention=True,
        kv_cache_type="q8_0",
        batch_size=1,
        cooldown_seconds=60,
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
        cooldown_seconds=60,
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
    gpu_clock_mhz: int | None = None
    windows_available_ram_gib: float | None = None
    windows_swap_used_gib: float | None = None


def parse_gpu_sample(output: str) -> ResourceSample:
    parts = output.strip().split(",")
    if len(parts) != 6:
        raise ValueError("GPU sensor malformed or multiple GPUs")
    memory, temperature, average, instant, utilization, clock = map(float, parts)
    values = (memory, temperature, average, instant, utilization, clock)
    if not all(math.isfinite(value) and value >= 0 for value in values):
        raise ValueError("Invalid GPU sensor value")
    if utilization > 100 or any(
        value != int(value) for value in (memory, temperature, utilization, clock)
    ):
        raise ValueError("Invalid GPU integral metric or utilization")
    return ResourceSample(
        0, 0, int(memory), int(temperature), max(average, instant), int(utilization), int(clock)
    )


def sample_resources(gpu: ResourceSample | None = None) -> ResourceSample:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", maxsplit=1)
        values[key] = int(value.split()[0]) * 1024
    if gpu is None:
        gpu = parse_gpu_sample(
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,temperature.gpu,power.draw.average,power.draw.instant,"
                    "utilization.gpu,clocks.current.graphics",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=0.5,
            )
        )
    return ResourceSample(
        available_ram_gib=values["MemAvailable"] / GIB,
        swap_used_gib=(values["SwapTotal"] - values["SwapFree"]) / GIB,
        gpu_memory_mib=gpu.gpu_memory_mib,
        gpu_temperature_c=gpu.gpu_temperature_c,
        gpu_power_w=gpu.gpu_power_w,
        gpu_utilization_pct=gpu.gpu_utilization_pct,
        gpu_clock_mhz=gpu.gpu_clock_mhz,
    )


def unsafe_reason(sample: ResourceSample, limits: ResourceLimits) -> str | None:
    values = (
        sample.available_ram_gib,
        sample.swap_used_gib,
        sample.gpu_memory_mib,
        sample.gpu_temperature_c,
        sample.gpu_power_w,
        sample.gpu_utilization_pct,
    )
    if not all(math.isfinite(value) and value >= 0 for value in values):
        return "monitor failure: invalid resource observation"
    if sample.gpu_utilization_pct > 100:
        return "monitor failure: invalid GPU utilization"
    if limits.maximum_gpu_clock_mhz is not None:
        if (
            sample.gpu_clock_mhz is None
            or not math.isfinite(sample.gpu_clock_mhz)
            or sample.gpu_clock_mhz < 0
        ):
            return "monitor failure: GPU clock observation missing or invalid"
        if sample.gpu_clock_mhz > limits.maximum_gpu_clock_mhz:
            return f"GPU clock {sample.gpu_clock_mhz} MHz exceeds cap"
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
    )
    return next((message for failed, message in checks if failed), None)
