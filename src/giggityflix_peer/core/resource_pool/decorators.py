"""
Unified decorators for resource management (Python 3.11+).

Features
--------
* @io_bound   – limits concurrent IO to the same physical drive.
* @cpu_bound  – runs CPU-heavy work in a process pool.

Both decorators
* support sync *and* async functions,
* auto-detect whether an event-loop is already running,
* are re-entrant (recursive calls run directly, avoiding executor loops).
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
from pathlib import Path
from typing import Any, Awaitable, Callable, ParamSpec, TypeVar, Union

from giggityflix_mgmt_peer.core.resource_pool.manager import get_resource_pool_manager

P = ParamSpec("P")
R = TypeVar("R")

# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

_in_io_pool:  contextvars.ContextVar[set[str]] = contextvars.ContextVar("_in_io_pool",  default=set())
_in_cpu_pool: contextvars.ContextVar[set[str]] = contextvars.ContextVar("_in_cpu_pool", default=set())


def _extract_arg(
    sig: inspect.Signature,
    param_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any | None:
    """Return the value bound to *param_name*, regardless of positional/kw-style."""
    bound = sig.bind_partial(*args, **kwargs)
    return bound.arguments.get(param_name)


def _run_sync(coro: Awaitable[R]) -> R:
    """Execute *coro* from sync code, re-using an existing loop if possible."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:             # no loop → easiest path
        return asyncio.run(coro)

    if loop.is_running():            # inside an event-loop (sync caller in async ctx)
        return asyncio.ensure_future(coro)          # type: ignore[return-value]
    return loop.run_until_complete(coro)            # type: ignore[return-value]

# --------------------------------------------------------------------------- #
# Decorators
# --------------------------------------------------------------------------- #

def io_bound(param_name: str = "filepath") -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Throttle IO to the drive of *param_name* (defaults to «filepath»)."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        sig      = inspect.signature(func)
        is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def _inner_async(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[name-defined]
            key          = func.__qualname__
            active_calls = _in_io_pool.get()

            # Inside IO-pool already → run directly.
            if key in active_calls:
                return await func(*args, **kwargs) if is_async else func(*args, **kwargs)  # type: ignore[return-value]

            path = _extract_arg(sig, param_name, args, kwargs)
            if path is None:                            # no path → nothing to throttle
                return await func(*args, **kwargs) if is_async else func(*args, **kwargs)  # type: ignore[return-value]

            mgr   = get_resource_pool_manager()
            sem   = mgr.get_drive_semaphore(Path(path))
            token = _in_io_pool.set(active_calls | {key})

            try:
                async with sem:
                    if is_async:
                        return await func(*args, **kwargs)          # type: ignore[return-value]
                    thread_pool = mgr.get_thread_pool()
                    loop        = asyncio.get_running_loop()
                    return await loop.run_in_executor(thread_pool, functools.partial(func, *args, **kwargs))
            finally:
                _in_io_pool.reset(token)

        @functools.wraps(func)
        def _inner_sync(*args: P.args, **kwargs: P.kwargs) -> R:      # type: ignore[name-defined]
            return _run_sync(_inner_async(*args, **kwargs))          # type: ignore[arg-type]

        return _inner_async if is_async else _inner_sync             # type: ignore[return-value]

    return decorator


def cpu_bound() -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Off-load CPU-intensive work to the process pool, with recursion guard."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        is_async = asyncio.iscoroutinefunction(func)

        @functools.wraps(func)
        async def _inner_async(*args: P.args, **kwargs: P.kwargs) -> R:  # type: ignore[name-defined]
            key          = func.__qualname__
            active_calls = _in_cpu_pool.get()

            if key in active_calls:                            # already inside pool
                return await func(*args, **kwargs) if is_async else func(*args, **kwargs)  # type: ignore[return-value]

            mgr        = get_resource_pool_manager()
            proc_pool  = mgr.get_process_pool()
            token      = _in_cpu_pool.set(active_calls | {key})

            try:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(proc_pool, functools.partial(func, *args, **kwargs))
            finally:
                _in_cpu_pool.reset(token)

        @functools.wraps(func)
        def _inner_sync(*args: P.args, **kwargs: P.kwargs) -> R:      # type: ignore[name-defined]
            return _run_sync(_inner_async(*args, **kwargs))          # type: ignore[arg-type]

        return _inner_async if is_async else _inner_sync             # type: ignore[return-value]

    return decorator

# --------------------------------------------------------------------------- #
# Parallel helper
# --------------------------------------------------------------------------- #

Task = Union[
    Callable[[], Awaitable[Any]],                         # naked coroutine function (lambda / partial / whatever)
    tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]],  # (func, args, kwargs)
]


async def execute_parallel(*tasks: Task) -> list[Any]:
    """
    Run *tasks* concurrently and return the ordered list of results.

    Each *task* may be:
    ───────────────────────────────────────────────────────────────────────────
    • an *awaitable* (callable coroutine) – awaited directly;
    • a triple ``(func, args, kwargs)``   – executed with its own decorators.
    """
    async def _run(callable_: Callable[..., Any], *a: Any, **kw: Any) -> Any:
        if asyncio.iscoroutinefunction(callable_):
            return await callable_(*a, **kw)
        return callable_(*a, **kw)

    coros: list[Awaitable[Any]] = []
    for t in tasks:
        if callable(t):
            coros.append(_run(t))
        elif isinstance(t, tuple) and len(t) >= 1:
            fn, a, kw = (t + ({},))[:3]  # pad kwargs default
            coros.append(_run(fn, *a, **kw))
        else:
            raise TypeError(f"Unsupported task spec: {t!r}")

    return await asyncio.gather(*coros)
