#!/usr/bin/env python3
"""Expose a local Bonsai endpoint on one explicit Tailscale address only."""

from __future__ import annotations

import argparse
import asyncio


async def _copy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(64 * 1024):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _handle(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    try:
        target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
    except OSError:
        client_writer.close()
        await client_writer.wait_closed()
        return

    await asyncio.gather(
        _copy(client_reader, target_writer),
        _copy(target_reader, client_writer),
        return_exceptions=True,
    )


async def _serve(args: argparse.Namespace) -> None:
    server = await asyncio.start_server(
        lambda reader, writer: _handle(reader, writer, args.target_host, args.target_port),
        host=args.listen_host,
        port=args.listen_port,
    )
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", required=True)
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    asyncio.run(_serve(parser.parse_args()))


if __name__ == "__main__":
    main()
