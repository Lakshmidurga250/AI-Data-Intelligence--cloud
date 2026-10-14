"""Safe synchronous bridge for running async worker coroutines in any execution context."""

import asyncio
import concurrent.futures
from typing import Any, Coroutine


def run_coroutine_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Execute an asyncio coroutine synchronously.
    Handles both standalone Celery worker processes (no active loop)
    and in-process eager execution under existing async frameworks (FastAPI/AnyIO/Pytest).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
