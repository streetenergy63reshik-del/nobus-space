"""Keep synchronous storage off the event loop; drain writes before cancellation."""
from __future__ import annotations

import asyncio


async def run_storage(operation, *args, on_cancel=None, **kwargs):
    """Finish one transaction, including late-lease cleanup, before returning STOP.

    Each store opens and closes its SQLite connection inside the worker. Never
    transfer a live connection or split a guarded transaction across threads.
    Repeated cancellation cannot detach the in-flight operation.
    """
    task = asyncio.create_task(asyncio.to_thread(operation, *args, **kwargs))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        if on_cancel is not None and result is not None:
            await run_storage(on_cancel, result)
        raise asyncio.CancelledError
    return result
