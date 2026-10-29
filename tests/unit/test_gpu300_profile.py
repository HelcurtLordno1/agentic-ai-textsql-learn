from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
from agentic_text2sql.contracts.sql import SqlCandidate
from agentic_text2sql.hardware import PROFILES, HardwareProfile, ProfileName
from agentic_text2sql.settings import Settings


def test_gpu300_profile_is_bounded_and_keeps_model_budgets() -> None:
    profile = PROFILES[ProfileName.QWEN_GPU300_F16_B16]
    settings = Settings(_env_file=None, **profile.ollama_environment())
    assert settings.gpu_execution_profile == profile.name.value
    assert settings.ollama_num_gpu == 41 and settings.ollama_num_batch == 16
    assert settings.ollama_num_thread == 8
    assert settings.run_deadline_seconds == 900 and settings.request_timeout_seconds == 300
    assert (
        settings.input_token_budget,
        settings.output_token_budget,
        settings.a1_max_requests,
    ) == (
        2800,
        768,
        3,
    )
    assert profile.limits.maximum_gpu_clock_mhz == 300
    assert profile.limits.maximum_gpu_power_w == 70
    assert not profile.flash_attention and profile.kv_cache_type == "f16"
    assert profile.keep_alive == "0" and profile.cooldown_seconds == 60


def test_actual_mock_http_sends_gpu41_batch16_and_retains_sampling() -> None:
    profile = PROFILES[ProfileName.QWEN_GPU300_F16_B16]

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["options"] == {
            "temperature": 0,
            "num_ctx": 4096,
            "num_predict": 768,
            "num_gpu": 41,
            "num_thread": 8,
            "num_batch": 16,
            "seed": 42,
        }
        assert body["keep_alive"] == 0 and body["think"] is False
        assert request.extensions["timeout"]["read"] == 300
        return httpx.Response(
            200, json={"message": {"content": '{"sql":"SELECT 1","confidence":1}'}}
        )

    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://fixture") as client:
        provider = OllamaProvider(
            Settings(_env_file=None, **profile.ollama_environment(), TEXT2SQL_GUARDED_RUN=True),
            client=client,
        )
        assert (
            provider.generate_structured(prompt="fixture", response_model=SqlCandidate).sql
            == "SELECT 1"
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"ollama_num_gpu": 20},
        {"prompt_batch_tokens": 64},
        {"flash_attention": True},
        {"kv_cache_type": "q8_0"},
        {"run_deadline_seconds": 901},
        {"keep_alive": "5m"},
        {"cooldown_seconds": 59},
        {"limits": {"maximum_gpu_clock_mhz": 350}},
        {"limits": {"maximum_gpu_clock_mhz": 300, "maximum_gpu_power_w": 71}},
    ],
)
def test_gpu300_name_cannot_license_a_different_envelope(overrides: dict[str, object]) -> None:
    body = PROFILES[ProfileName.QWEN_GPU300_F16_B16].model_dump(mode="json")
    body.update(overrides)
    with pytest.raises(ValidationError):
        HardwareProfile.model_validate(body)


@pytest.mark.parametrize(
    "overrides",
    [
        {"TEXT2SQL_OLLAMA_NUM_GPU": 0},
        {"TEXT2SQL_OLLAMA_NUM_BATCH": 64},
        {"TEXT2SQL_OLLAMA_NUM_THREAD": 16},
        {"TEXT2SQL_REQUEST_TIMEOUT_SECONDS": 301},
        {"TEXT2SQL_RUN_DEADLINE_SECONDS": 901},
    ],
)
def test_settings_profile_tag_is_not_a_blanket_deadline_bypass(
    overrides: dict[str, object],
) -> None:
    environment: dict[str, object] = dict(
        PROFILES[ProfileName.QWEN_GPU300_F16_B16].ollama_environment()
    )
    environment.update(overrides)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **environment)


def test_old_profiles_are_byte_equivalent_to_the_protected_cpu_checkout() -> None:
    snapshot = json.loads(
        (Path(__file__).parents[1] / "fixtures/hardware_profiles_v5.json").read_text()
    )
    for name, original in snapshot.items():
        profile = PROFILES[ProfileName(name)]
        assert profile.model_dump(mode="json") == original
        assert "TEXT2SQL_GPU_EXECUTION_PROFILE" not in profile.ollama_environment()
