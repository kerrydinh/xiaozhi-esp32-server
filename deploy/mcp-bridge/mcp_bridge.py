"""Connect stdio MCP servers to a XiaoZhi MCP endpoint.

Reads mcp_config.json (the same "mcpServers" format as XiaoZhi's mcp_pipe.py,
stdio servers only):

    {"mcpServers": {"name": {"command": "...", "args": [...], "env": {...},
                             "disabled": false}}}

For each enabled server it opens a WebSocket to $MCP_ENDPOINT (the agent's
address from the console), starts the server process and copies JSON-RPC
messages both ways, one message per line on stdio. When either side ends, the
process is stopped and both are restarted with backoff. "${VAR}" in args and
env values is replaced from the environment.
"""
import asyncio
import json
import logging
import os
import signal
import sys

import websockets

log = logging.getLogger("mcp-bridge")
MAX_LINE = 16 * 1024 * 1024  # search results can be large single-line messages


async def ws_to_process(ws, proc):
    async for message in ws:
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        proc.stdin.write(message.rstrip("\n").encode("utf-8") + b"\n")
        await proc.stdin.drain()


async def process_to_ws(proc, ws):
    while line := await proc.stdout.readline():
        line = line.decode("utf-8").strip()
        if line:
            await ws.send(line)


async def log_stderr(proc, name):
    while line := await proc.stderr.readline():
        log.info("[%s] %s", name, line.decode("utf-8", "replace").rstrip())


async def serve(name, entry, endpoint):
    command = [os.path.expandvars(entry["command"])]
    command += [os.path.expandvars(str(a)) for a in entry.get("args", [])]
    env = dict(os.environ)
    env.update({k: os.path.expandvars(str(v)) for k, v in (entry.get("env") or {}).items()})
    backoff = 1
    while True:
        proc = None
        try:
            async with websockets.connect(endpoint, ping_interval=30, ping_timeout=30, max_size=None) as ws:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    limit=MAX_LINE,
                )
                log.info("%s: connected to the endpoint, started %s", name, command[0])
                backoff = 1
                tasks = [
                    asyncio.create_task(ws_to_process(ws, proc)),
                    asyncio.create_task(process_to_ws(proc, ws)),
                    asyncio.create_task(log_stderr(proc, name)),
                ]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                for task in done:
                    if task.exception():
                        log.warning("%s: %s", name, task.exception())
                log.warning("%s: endpoint connection or server process ended", name)
        except Exception as e:  # connection refused, invalid token, ...
            log.warning("%s: %s", name, e)
        finally:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
        log.info("%s: reconnecting in %ds", name, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    endpoint = os.environ.get("MCP_ENDPOINT", "").strip()
    if not endpoint.startswith(("ws://", "wss://")):
        sys.exit("Set MCP_ENDPOINT to the agent's MCP endpoint address (ws://.../mcp_endpoint/mcp/?token=...)")
    path = os.environ.get("MCP_CONFIG", "mcp_config.json")
    with open(path, encoding="utf-8") as f:
        servers = json.load(f).get("mcpServers", {})
    enabled = {n: e for n, e in servers.items() if not e.get("disabled")}
    if not enabled:
        sys.exit(f"No enabled servers in {path}")
    log.info("Bridging %s to %s", ", ".join(enabled), endpoint.split("?")[0])

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    tasks = [asyncio.create_task(serve(n, e, endpoint)) for n, e in enabled.items()]
    await stop.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
