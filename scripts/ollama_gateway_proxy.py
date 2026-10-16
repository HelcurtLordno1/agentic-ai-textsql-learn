"""Stable loopback URL for an owned Windows backend across WSL gateway changes."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await asyncio.wait_for(reader.read(65536), timeout=240):
        writer.write(data)
        await writer.drain()


async def serve(port: int, gateway: str, backend_port: int) -> None:
    slots = asyncio.Semaphore(16)

    async def connect(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        remote: asyncio.StreamWriter | None = None
        tasks: list[asyncio.Task[None]] = []
        try:
            async with slots:
                target, remote = await asyncio.wait_for(
                    asyncio.open_connection(gateway, backend_port), timeout=2
                )
                tasks = [
                    asyncio.create_task(relay(reader, remote)),
                    asyncio.create_task(relay(target, writer)),
                ]
                await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except (OSError, TimeoutError):
            pass
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

    server = await asyncio.start_server(connect, "127.0.0.1", port, limit=65536)
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--backend-port", required=True, type=int)
    args = parser.parse_args()
    if not ipaddress.ip_address(args.gateway).is_private:
        parser.error("WSL gateway must be private")
    if not all(1024 <= port <= 65535 for port in (args.port, args.backend_port)):
        parser.error("Ports must be in 1024..65535")
    try:
        asyncio.run(serve(args.port, args.gateway, args.backend_port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
