"""Actual candidate ASGI/static app over loopback TCP, with no product substitute."""

import asyncio
from contextlib import asynccontextmanager
import socket

import uvicorn

from src.transport.miniapp import create_miniapp_app


@asynccontextmanager
async def candidate_server(core, *, port=0):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", port))
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    app = create_miniapp_app(core, allowed_host="127.0.0.1", allowed_origin=origin)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", log_config=None, log_level="critical",
        access_log=False, timeout_graceful_shutdown=3,
    ))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("candidate_server_start_failed")
                await asyncio.sleep(0.01)
        yield origin
    finally:
        server.should_exit = True
        try:
            async with asyncio.timeout(5):
                await asyncio.shield(task)
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise RuntimeError("candidate_server_cleanup_unproven") from None
        finally:
            listener.close()
