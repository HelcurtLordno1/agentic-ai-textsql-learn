from __future__ import annotations

import asyncio
from contextlib import suppress
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.ollama_gateway_proxy import bounded_idle_timeout, forward_connection
from scripts.tmux_benchmarks import SequencePlan
from scripts.tmux_experiment import ExperimentPlan


@pytest.mark.parametrize("request_seconds,expected", [(120, 240), (180, 240), (300, 330)])
def test_proxy_outlives_existing_bounded_request(request_seconds: float, expected: float) -> None:
    assert bounded_idle_timeout(request_seconds) == expected


@pytest.mark.parametrize("request_seconds", [0, -1, 301, float("inf"), float("nan")])
def test_unbounded_or_invalid_timeout_refused(request_seconds: float) -> None:
    with pytest.raises(ValueError):
        bounded_idle_timeout(request_seconds)


async def delayed_exchange(idle_timeout: float) -> bytes:
    """Real TCP peers; client stays silent while a bounded backend computes."""
    handlers: set[asyncio.Task[None]] = set()

    async def backend(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        handlers.add(task)
        try:
            await reader.readuntil(b"\r\n\r\n")
            await asyncio.sleep(0.3)
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nready")
            await writer.drain()
        finally:
            writer.close()
            with suppress(ConnectionError):
                await writer.wait_closed()
            handlers.discard(task)

    backend_server = await asyncio.start_server(backend, "127.0.0.1", 0)
    backend_port = backend_server.sockets[0].getsockname()[1]

    async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await forward_connection(
            reader,
            writer,
            gateway="127.0.0.1",
            backend_port=backend_port,
            idle_timeout_seconds=idle_timeout,
        )

    proxy_server = await asyncio.start_server(proxy, "127.0.0.1", 0)
    try:
        reader, writer = await asyncio.open_connection(
            "127.0.0.1", proxy_server.sockets[0].getsockname()[1]
        )
        writer.write(b"GET /slow-fixture HTTP/1.1\r\nHost: local\r\n\r\n")
        await writer.drain()
        result = await asyncio.wait_for(reader.read(), 2)
        writer.close()
        await writer.wait_closed()
        return result
    finally:
        proxy_server.close()
        backend_server.close()
        await proxy_server.wait_closed()
        await backend_server.wait_closed()
        await asyncio.gather(*handlers, return_exceptions=True)


def test_reproduces_legacy_premature_disconnect_during_silent_request() -> None:
    assert asyncio.run(delayed_exchange(0.15)) == b""


def test_bounded_transport_preserves_delayed_response() -> None:
    assert asyncio.run(delayed_exchange(0.6)).endswith(b"ready")


def test_olist_only_plan_does_not_schedule_spider(tmp_path: Path) -> None:
    def child(suite: str) -> ExperimentPlan:
        return ExperimentPlan(
            name="fixture-" + suite,
            suite=suite,
            variant="v5-contracts",
            root=str(tmp_path),
            predictions=str(tmp_path / (suite + ".jsonl")),
            report=str(tmp_path / (suite + ".json")),
            wrapper_args=(),
            settings_environment={},
            dotenv_sha256=None,
        )

    plan = SequencePlan(
        name="fixture",
        spider=child("spider"),
        olist=child("olist"),
        models_dir=str(tmp_path),
        suites=("olist",),
    )
    assert [p.suite for p in plan.benchmarks] == ["olist"]
    assert SequencePlan.model_validate_json(plan.model_dump_json()) == plan
    for suites in [(), ("olist", "olist")]:
        body = plan.model_dump()
        body["suites"] = suites
        with pytest.raises(ValidationError):
            SequencePlan.model_validate(body)
