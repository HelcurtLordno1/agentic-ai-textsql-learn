from agentic_text2sql.hardware import (
    PROFILES,
    ProfileName,
    ResourceLimits,
    ResourceSample,
    unsafe_reason,
)


def test_resource_guard_fails_closed_for_each_threshold() -> None:
    safe = ResourceSample(15, 0, 3000, 60, 50, 100)
    limits = ResourceLimits()
    assert unsafe_reason(safe, limits) is None
    assert "available RAM" in str(unsafe_reason(ResourceSample(13, 0, 3000, 60, 50, 100), limits))
    assert "swap" in str(unsafe_reason(ResourceSample(15, 0.25, 3000, 60, 50, 100), limits))
    assert "VRAM" in str(unsafe_reason(ResourceSample(15, 0, 6144, 60, 50, 100), limits))
    assert "temperature" in str(unsafe_reason(ResourceSample(15, 0, 3000, 68, 50, 100), limits))
    assert "power" in str(unsafe_reason(ResourceSample(15, 0, 3000, 60, 70, 100), limits))


def test_profiles_bound_parallelism_and_long_run_unloads() -> None:
    interactive = PROFILES[ProfileName.INTERACTIVE]
    acceptance = PROFILES[ProfileName.ACCEPTANCE]
    assert interactive.ollama_environment()["OLLAMA_NUM_PARALLEL"] == "1"
    assert interactive.max_loaded_models == 1
    assert interactive.ollama_num_gpu == 1
    assert acceptance.batch_size == 1
    assert acceptance.keep_alive == "0"
    assert acceptance.cooldown_seconds == 60


def test_v4_600_b16_changes_only_clock_and_prompt_batch_from_full_gpu() -> None:
    import json

    import httpx

    from agentic_text2sql.adapters.llm.ollama_provider import OllamaProvider
    from agentic_text2sql.contracts.sql import SqlCandidate
    from agentic_text2sql.settings import Settings

    old = PROFILES[ProfileName.QWEN_FULL_GPU]
    new = PROFILES[ProfileName.QWEN_V4_600_B16]
    assert new.model_dump(exclude={"name", "description", "limits", "prompt_batch_tokens"}) == (
        old.model_dump(exclude={"name", "description", "limits", "prompt_batch_tokens"})
    )
    assert new.limits.model_dump(exclude={"maximum_gpu_clock_mhz"}) == old.limits.model_dump(
        exclude={"maximum_gpu_clock_mhz"}
    )
    assert new.limits.maximum_gpu_clock_mhz == 600
    assert all(
        p.prompt_batch_tokens == 64
        for key, p in PROFILES.items()
        if key not in {new.name, ProfileName.QWEN_GPU300_F16_B16}
    )

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["options"]["num_gpu"] == 41
        assert body["options"]["num_batch"] == 16
        assert body["options"]["num_thread"] == 8
        assert body["options"]["num_ctx"] == 4096
        assert body["options"]["num_predict"] == 768
        assert body["keep_alive"] == 0
        return httpx.Response(
            200, json={"message": {"content": '{"sql":"SELECT 1","confidence":1}'}}
        )

    settings = Settings(**new.ollama_environment(), TEXT2SQL_GUARDED_RUN=True)
    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        OllamaProvider(settings, client=client).generate_structured(
            prompt="test", response_model=SqlCandidate
        )
