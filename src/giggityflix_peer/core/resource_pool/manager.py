"""
Dynamic resource-pool manager for CPU and IO tasks (Python 3.11+).

• ProcessPoolExecutor  – resizable at runtime.
• ThreadPoolExecutor   – resizable at runtime (for sync IO wrappers).
• Per-drive, resizable semaphores limiting concurrent IO.
• Public helpers:
      - get_process_pool()
      - get_thread_pool()
      - get_drive_semaphore(path)
      - submit_cpu_task(func, *a, **kw)
      - submit_io_task(filepath, func, *a, **kw)
      - reload_config()               ← re-reads limits from configuration_service
"""

from __future__ import annotations

import asyncio
import os
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

# --------------------------------------------------------------------------- #
# Resizable semaphores
# --------------------------------------------------------------------------- #

class ResizableAsyncSemaphore:
    """An asyncio.Semaphore whose capacity can be changed at runtime."""

    def __init__(self, value: int) -> None:
        self._max     = value
        self._value   = value
        self._cond    = asyncio.Condition()

    async def acquire(self) -> None:
        async with self._cond:
            while self._value <= 0:
                await self._cond.wait()
            self._value -= 1

    async def release(self) -> None:
        async with self._cond:
            self._value += 1
            self._cond.notify()

    async def __aenter__(self) -> "ResizableAsyncSemaphore":
        await self.acquire()
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.release()

    async def resize(self, new_limit: int) -> None:
        """Increase or decrease the maximum concurrency."""
        async with self._cond:
            delta      = new_limit - self._max
            self._max  = new_limit
            self._value += delta
            if delta > 0:
                # Make new permits visible immediately
                self._cond.notify_all()
            else:
                # If shrunk, don't take permits away from tasks already inside.
                # New acquires will block until outstanding releases bring
                # the counter below the lowered ceiling.
                self._value = max(self._value, 0)


class ResizableBoundedSemaphore(threading.Semaphore):
    """threading.Semaphore variant with a runtime-adjustable upper bound."""

    def __init__(self, value: int):
        super().__init__(value)
        self._max = value
        self._lock = threading.Lock()

    def resize(self, new_limit: int) -> None:
        with self._lock:
            delta   = new_limit - self._max
            self._max = new_limit
            if delta > 0:
                # release() the extra permits
                for _ in range(delta):
                    super().release()
            # On decrease we simply lower the ceiling; outstanding holders
            # finish naturally and new acquire()s will block.

    # Ensure ._value never grows past ._max
    def release(self) -> None:                              # type: ignore[override]
        with self._lock:
            if self._value >= self._max:
                raise ValueError("Semaphore released too many times")
            super().release()

# --------------------------------------------------------------------------- #
# Configuration source (stub)
# --------------------------------------------------------------------------- #

def _fetch_limits() -> dict[str, Any]:
    """
    Pretend-DB call via configuration_service.

    Returns
    -------
    {
        'cpu_pool':            6,                # processes
        'io_pool_threads':     32,               # threads
        'drive_limits': {      # concurrent IO per physical disk
            'C': 8,
            'D': 4
        }
    }
    """
    # TODO: inject real ConfigurationService here
    return {
        "cpu_pool":         int(os.getenv("CPU_POOL",          6)),
        "io_pool_threads":  int(os.getenv("IO_POOL_THREADS",  32)),
        "drive_limits": {
            "C": int(os.getenv("DRIVE_C_LIMIT", 8)),
            "D": int(os.getenv("DRIVE_D_LIMIT", 4)),
        },
    }

# --------------------------------------------------------------------------- #
# Resource-pool manager (singleton)
# --------------------------------------------------------------------------- #

class ResourcePoolManager:
    _instance: "ResourcePoolManager | None" = None
    _global_lock = threading.Lock()

    def __new__(cls) -> "ResourcePoolManager":              # pragma: no cover
        with cls._global_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    # ---- life-cycle ------------------------------------------------------- #

    def _init(self) -> None:
        self._loop = asyncio.get_event_loop_policy().get_event_loop()
        self._process_pool: ProcessPoolExecutor | None = None
        self._thread_pool:  ThreadPoolExecutor  | None = None
        self._drive_sems: dict[str, ResizableAsyncSemaphore] = {}
        self.reload_config(warm=True)

    def close(self) -> None:
        if self._process_pool:
            self._process_pool.shutdown(cancel_futures=True)
        if self._thread_pool:
            self._thread_pool.shutdown(cancel_futures=True)

    # ---- public API ------------------------------------------------------- #

    # executors .............................

    def get_process_pool(self) -> ProcessPoolExecutor:
        return self._process_pool                         # type: ignore[return-value]

    def get_thread_pool(self) -> ThreadPoolExecutor:
        return self._thread_pool                          # type: ignore[return-value]

    # semaphores ............................

    def get_drive_semaphore(self, path: str | Path) -> ResizableAsyncSemaphore:
        drive = self._get_drive_id_for_path(str(path))
        try:
            return self._drive_sems[drive]
        except KeyError:
            # Fallback: if drive not in config, lazily create trivial semaphore
            sem = ResizableAsyncSemaphore(32)
            self._drive_sems[drive] = sem
            return sem

    # task helpers ...........................

    async def submit_io_task(
        self,
        filepath: str | Path,
        func: Callable[..., Any],
        *a: Any,
        **kw: Any,
    ) -> Any:
        sem  = self.get_drive_semaphore(filepath)

        async with sem:                                   # FIFO fairness
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._thread_pool,
                lambda: func(*a, **kw),
            )

    async def submit_cpu_task(
        self,
        func: Callable[..., Any],
        *a: Any,
        **kw: Any,
    ) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._process_pool,
            lambda: func(*a, **kw),
        )

    # ---- dynamic resizing ------------------------------------------------- #

    def reload_config(self, warm: bool = False) -> None:
        """
        Re-read limits and resize pools/semaphores on the fly.

        *warm* is used during first initialisation to avoid the cost of
        shutting down freshly created executors.
        """
        limits = _fetch_limits()

        # 1) Process-pool ----------------------------------------------------
        new_proc_size = limits["cpu_pool"]
        if not self._process_pool:                        # first run
            self._process_pool = ProcessPoolExecutor(max_workers=new_proc_size)
        elif new_proc_size != self._process_pool._max_workers:
            old = self._process_pool
            self._process_pool = ProcessPoolExecutor(max_workers=new_proc_size)
            if not warm:
                old.shutdown(cancel_futures=False)

        # 2) Thread-pool -----------------------------------------------------
        new_thread_size = limits["io_pool_threads"]
        if not self._thread_pool:
            self._thread_pool = ThreadPoolExecutor(max_workers=new_thread_size)
        elif new_thread_size != self._thread_pool._max_workers:
            old = self._thread_pool
            self._thread_pool = ThreadPoolExecutor(max_workers=new_thread_size)
            if not warm:
                old.shutdown(cancel_futures=False)

        # 3) Per-drive semaphores -------------------------------------------
        self._update_drive_limits(limits["drive_limits"])

    # -------------------------------------------------------------------- #

    # Helpers

    @staticmethod
    def _get_drive_id_for_path(path: str) -> str:
        """Return physical drive ID – naïve Windows/unix split."""
        p = Path(path).resolve()
        if os.name == "nt":
            return p.drive.rstrip(":").upper() or "C"
        return p.anchor or "/"

    def _update_drive_limits(self, mapping: Mapping[str, int]) -> None:
        """Resize existing semaphores and create new ones on demand."""
        for drive, cap in mapping.items():
            if drive in self._drive_sems:
                sem = self._drive_sems[drive]
                # resize asynchronously in the main loop
                asyncio.run_coroutine_threadsafe(sem.resize(cap), self._loop)
            else:
                self._drive_sems[drive] = ResizableAsyncSemaphore(cap)

        # Remove semaphores whose drive disappeared from config
        for obsolete in set(self._drive_sems) - set(mapping):
            # Optionally: keep them alive until outstanding users release.
            # Here, we simply leave them — safer for in-flight tasks.
            pass


# convenience alias for callers
def get_resource_pool_manager() -> ResourcePoolManager:
    return ResourcePoolManager()
