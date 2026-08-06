"""Read-only environment diagnostics used by the CLI and tests."""

from __future__ import annotations

import shutil
import subprocess
import sys
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.exceptions import ProviderUnavailableError
from agentic_text2sql.settings import Settings


class CheckStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class DoctorCheck(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    status: CheckStatus
    detail: str


class DoctorReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    checks: tuple[DoctorCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.status is not CheckStatus.FAIL for check in self.checks)


def _path_check(name: str, path: Path, *, create: bool = False) -> DoctorCheck:
    try:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        writable = path.is_dir() and os_access_writable(path)
    except OSError as exc:
        return DoctorCheck(
            name=name, status=CheckStatus.FAIL, detail=f"{path}: {type(exc).__name__}"
        )
    status = CheckStatus.PASS if writable else CheckStatus.FAIL
    return DoctorCheck(name=name, status=status, detail=f"{path} (writable={writable})")


def os_access_writable(path: Path) -> bool:
    """Check directory write bits without creating probe files."""
    import os

    return os.access(path, os.W_OK | os.X_OK)


def _gpu_check() -> DoctorCheck:
    binary = shutil.which("nvidia-smi")
    if binary is None:
        return DoctorCheck(name="gpu", status=CheckStatus.WARN, detail="nvidia-smi not found")
    try:
        result = subprocess.run(
            [binary, "--query-gpu=name,memory.total", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DoctorCheck(name="gpu", status=CheckStatus.WARN, detail=type(exc).__name__)
    return DoctorCheck(name="gpu", status=CheckStatus.PASS, detail=result.stdout.strip())


def run_doctor(
    settings: Settings | None = None, provider: OllamaProvider | None = None
) -> DoctorReport:
    config = settings or Settings()
    checks = [
        DoctorCheck(
            name="python",
            status=CheckStatus.PASS if sys.version_info[:2] == (3, 12) else CheckStatus.FAIL,
            detail=sys.version.split()[0],
        ),
        _path_check("project_root", config.project_root),
        _path_check("data_dir", config.resolved_data_dir, create=True),
        _path_check("artifact_dir", config.resolved_artifact_dir, create=True),
        _gpu_check(),
    ]
    owns_provider = provider is None
    active_provider = provider or OllamaProvider(config)
    try:
        version = active_provider.version()
        checks.append(
            DoctorCheck(name="ollama", status=CheckStatus.PASS, detail=f"version={version}")
        )
        model_names = {
            str(item.get("name") or item.get("model")) for item in active_provider.list_models()
        }
        found = config.ollama_model in model_names
        checks.append(
            DoctorCheck(
                name="model",
                status=CheckStatus.PASS if found else CheckStatus.FAIL,
                detail=f"{config.ollama_model} installed={found}",
            )
        )
    except ProviderUnavailableError as exc:
        checks.append(DoctorCheck(name="ollama", status=CheckStatus.FAIL, detail=str(exc)))
    finally:
        if owns_provider:
            active_provider.close()
    usage = shutil.disk_usage(config.resolved_data_dir)
    checks.append(
        DoctorCheck(
            name="disk",
            status=CheckStatus.PASS if usage.free >= 5 * 1024**3 else CheckStatus.WARN,
            detail=f"free_gib={usage.free / 1024**3:.1f}",
        )
    )
    return DoctorReport(checks=tuple(checks))
