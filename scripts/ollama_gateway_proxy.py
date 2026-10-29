"""Stable loopback URL for an owned Windows backend across WSL gateway changes."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import math


def bounded_idle_timeout(request_timeout_seconds: float) -> float:
    """The transport must outlive the caller's bounded HTTP request."""
    if not math.isfinite(request_timeout_seconds) or not 0 < request_timeout_seconds <= 300:
        raise ValueError("Request timeout must be in (0, 300] seconds")
    return max(240.0, request_timeout_seconds + 30.0)


async def relay(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, idle_timeout_seconds: float = 240
) -> None:
    while data := await asyncio.wait_for(reader.read(65536), timeout=idle_timeout_seconds):
        writer.write(data)
        await writer.drain()


async def forward_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    gateway: str,
    backend_port: int,
    idle_timeout_seconds: float,
) -> None:
    remote: asyncio.StreamWriter | None = None
    tasks: list[asyncio.Task[None]] = []
    try:
        target, remote = await asyncio.wait_for(
            asyncio.open_connection(gateway, backend_port), timeout=2
        )
        tasks = [
            asyncio.create_task(relay(reader, remote, idle_timeout_seconds)),
            asyncio.create_task(relay(target, writer, idle_timeout_seconds)),
        ]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()  # Surface relay failure before closing both owned streams.
    except (OSError, TimeoutError) as exc:
        logging.getLogger(__name__).warning(
            "Gateway relay closed: %s; idle_timeout_seconds=%s",
            type(exc).__name__,
            idle_timeout_seconds,
        )
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        writer.close()
        if remote is not None:
            remote.close()
        await asyncio.gather(
            writer.wait_closed(),
            *([remote.wait_closed()] if remote is not None else []),
            return_exceptions=True,
        )


async def serve(
    port: int, gateway: str, backend_port: int, idle_timeout_seconds: float = 240
) -> None:
    slots = asyncio.Semaphore(16)

    async def connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async with slots:
            await forward_connection(
                reader,
                writer,
                gateway=gateway,
                backend_port=backend_port,
                idle_timeout_seconds=idle_timeout_seconds,
            )

    server = await asyncio.start_server(connect, "127.0.0.1", port, limit=65536)
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--backend-port", required=True, type=int)
    parser.add_argument("--request-timeout-seconds", type=float, default=120)
    args = parser.parse_args()
    try:
        idle_timeout = bounded_idle_timeout(args.request_timeout_seconds)
    except ValueError as exc:
        parser.error(str(exc))
    if not ipaddress.ip_address(args.gateway).is_private:
        parser.error("WSL gateway must be private")
    if not all(1024 <= port <= 65535 for port in (args.port, args.backend_port)):
        parser.error("Ports must be in 1024..65535")
    print(
        f"OWNED GATEWAY CONFIG: request_timeout_seconds={args.request_timeout_seconds} "
        f"idle_timeout_seconds={idle_timeout}",
        flush=True,
    )
    try:
        asyncio.run(serve(args.port, args.gateway, args.backend_port, idle_timeout))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
