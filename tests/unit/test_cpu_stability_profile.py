from __future__ import annotations

import io
import json
import subprocess
import sys
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.contracts.sql import SqlCandidate
from agentic_text2sql.hardware import PROFILES, ProfileName
from agentic_text2sql.settings import Settings
from scripts import tmux_benchmarks


def test_cpu_profile_preserves_safety_and_budgets_but_removes_cuda() -> None:
    cpu = PROFILES[ProfileName.QWEN_CPU_600_STABLE]
    gpu = PROFILES[ProfileName.QWEN_V4_600_B16]
    assert cpu.limits == gpu.limits
    assert cpu.ollama_num_gpu == 0 and cpu.cpu_cores == 8
    assert cpu.prompt_batch_tokens == 64
    assert not cpu.flash_attention and cpu.kv_cache_type == "f16"
    assert cpu.batch_size == 1 and cpu.keep_alive == "0" and cpu.cooldown_seconds == 60
    settings = Settings(_env_file=None, **cpu.ollama_environment())
    assert settings.run_deadline_seconds == 900 and settings.request_timeout_seconds == 300
    assert settings.input_token_budget == 2800 and settings.output_token_budget == 768
    assert settings.a1_max_requests == 3
    for key, profile in PROFILES.items():
        if key != ProfileName.QWEN_CPU_600_STABLE:
            assert profile.run_deadline_seconds <= 180 and profile.request_timeout_seconds == 120


def test_cpu_generation_sends_gpu_zero_to_actual_http_boundary() -> None:
    profile = PROFILES[ProfileName.QWEN_CPU_600_STABLE]

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["options"]["num_gpu"] == 0
        assert body["options"]["num_thread"] == 8
        assert body["options"]["num_batch"] == 64
        assert body["options"]["num_ctx"] == 4096
        assert body["options"]["num_predict"] == 768 and body["keep_alive"] == 0
        assert request.extensions["timeout"]["read"] == 300
        return httpx.Response(
            200, json={"message": {"content": '{"sql":"SELECT 1","confidence":1}'}}
        )

    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        settings = Settings(
            _env_file=None, **profile.ollama_environment(), TEXT2SQL_GUARDED_RUN=True
        )
        OllamaProvider(settings, client=client).generate_structured(
            prompt="test", response_model=SqlCandidate
        )


@pytest.mark.parametrize("layers,deadline", [(41, 181), (None, 900), (0, 901)])
def test_long_deadline_cannot_silently_apply_to_gpu_or_be_unbounded(layers, deadline) -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, TEXT2SQL_OLLAMA_NUM_GPU=layers, TEXT2SQL_RUN_DEADLINE_SECONDS=deadline
        )


@pytest.mark.parametrize(
    "profile_name,fa,kv",
    [(ProfileName.QWEN_CPU_600_STABLE, "0", "f16"), (ProfileName.QWEN_V4_600_B16, "1", "q8_0")],
)
def test_owned_native_launcher_receives_profile_cache_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile_name, fa, kv
) -> None:
    commands = []
    original_client = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.port != 11434:
            raise httpx.ConnectError("unoccupied", request=request)
        return httpx.Response(200, json={"models": []})

    monkeypatch.setattr(tmux_benchmarks, "directory", lambda plan: tmp_path)
    monkeypatch.setattr(tmux_benchmarks, "frozen_environment", lambda child: {})
    monkeypatch.setattr(tmux_benchmarks, "windows_path", str)
    monkeypatch.setattr(
        tmux_benchmarks.subprocess, "check_output", lambda *a, **k: "default via 172.0.0.1"
    )
    monkeypatch.setattr(
        tmux_benchmarks.httpx,
        "Client",
        lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw),
    )

    def launch(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(pid=1234)

    monkeypatch.setattr(tmux_benchmarks.subprocess, "Popen", launch)
    plan = SimpleNamespace(
        profile=profile_name,
        spider=SimpleNamespace(python_executable=sys.executable),
        server_port=11435,
        backend_port=11436,
        models_dir=str(tmp_path),
    )
    owner = tmux_benchmarks.OwnedServer(plan, io.StringIO())
    try:
        assert owner.start() == 1234
        native = commands[0]
        assert native[native.index("-FlashAttention") + 1] == fa
        assert native[native.index("-KvCacheType") + 1] == kv
    finally:
        if owner.handle:
            owner.handle.close()


def test_cpu_worker_cleanup_keeps_heartbeat_past_old_two_hundred_second_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elapsed = 0.0
    beats = []

    class Worker:
        def poll(self):
            return 0 if elapsed >= 960 else None

        def wait(self, timeout):
            nonlocal elapsed
            elapsed += timeout
            if elapsed < 960:
                raise subprocess.TimeoutExpired("cooling", timeout)
            return 0

    monkeypatch.setattr(tmux_benchmarks.time, "monotonic", lambda: elapsed)
    profile = PROFILES[ProfileName.QWEN_CPU_600_STABLE]
    timeout = profile.run_deadline_seconds + profile.cooldown_seconds + 30
    tmux_benchmarks.wait_worker_cleanup(
        Worker(), SimpleNamespace(heartbeat=lambda: beats.append(elapsed)), timeout
    )
    assert elapsed >= 960 and beats[-1] > 959
    assert max(b - a for a, b in pairwise(beats)) <= 0.21
