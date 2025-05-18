import asyncio
import concurrent.futures
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, Set

from .utils.resizable_semaphore import ResizableSemaphore
from ..services.config_service import config_service

T = TypeVar('T')
R = TypeVar('R')


class MetricsCollector:
    """Collects and reports execution metrics."""

    def __init__(self, enabled: bool = True, logger: Optional[Callable] = None):
        self.enabled = enabled
        self.logger = logger or print

    def record_operation(self, resource_type: str, operation_name: str,
                         queue_time: float, execution_time: float):
        """Record metrics for an operation."""
        if self.enabled:
            self.logger(f"[{resource_type}] {operation_name}: " +
                        f"Queued for {queue_time:.4f}s, " +
                        f"Executed in {execution_time:.4f}s")


class ExecutionMetrics:
    """Tracks execution metrics for operations."""

    def __init__(self, operation_name: str, resource_type: str, collector: MetricsCollector):
        self.operation_name = operation_name
        self.resource_type = resource_type
        self.collector = collector
        self.start_time = None
        self.queue_time = None
        self.execution_time = None

    def mark_queued(self):
        """Mark when a task is queued."""
        self.start_time = time.time()

    def mark_started(self):
        """Mark when a task starts executing."""
        if self.start_time:
            # Ensure queue_time is always a float
            self.queue_time = float(time.time() - self.start_time)

    def mark_completed(self):
        """Mark when a task is completed."""
        if self.start_time:
            # Calculate total time and ensure it's a float
            total_time = float(time.time() - self.start_time)
            # Calculate actual execution time
            self.execution_time = total_time
            if self.queue_time:
                self.execution_time = float(total_time - self.queue_time)
            else:
                self.queue_time = 0.0  # Ensure queue_time is always a float

            # Report metrics
            self.collector.record_operation(
                self.resource_type,
                self.operation_name,
                self.queue_time,
                self.execution_time
            )


class ResourcePoolManager:
    """Manages resource pools for IO and CPU operations."""

    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        self.metrics_collector = metrics_collector or MetricsCollector()

        # Initialize with defaults, will be updated in start()
        self._process_pool_size = os.cpu_count() or 4
        self._default_io_limit = 2

        # Initialize the process pool
        # Use ThreadPoolExecutor instead of ProcessPoolExecutor in tests
        import os
        if os.environ.get('PYTEST_CURRENT_TEST'):
            self._cpu_pool = concurrent.futures.ThreadPoolExecutor(
                max_workers=self._process_pool_size
            )
        else:
            self._cpu_pool = concurrent.futures.ProcessPoolExecutor(
                max_workers=self._process_pool_size
            )

        # Semaphores for IO control
        self._io_semaphores: Dict[str, ResizableSemaphore] = {}
        self._semaphore_sizes: Dict[str, int] = {}  # Track semaphore sizes
        self._io_semaphores_lock = threading.Lock()

        # Track active CPU tasks for safe pool resizing
        self._active_cpu_tasks: Set[int] = set()
        self._cpu_task_lock = threading.Lock()
        self._cpu_pool_lock = threading.Lock()
        self._resize_pending = False
        self._old_pool = None  # Store old pool for cleanup

    async def start(self):
        """Start the resource pool manager."""
        # Load configuration
        self._process_pool_size = await config_service.get("process_pool_size", os.cpu_count() or 4)
        self._default_io_limit = await config_service.get("default_io_limit", 2)

        # Resize process pool to match configuration
        self.resize_process_pool(self._process_pool_size)

    async def get_io_semaphore(self, filepath: str) -> ResizableSemaphore:
        """Get or create a semaphore for the drive containing the file."""
        storage_path = self._get_storage_path(filepath)

        with self._io_semaphores_lock:
            if storage_path not in self._io_semaphores:
                # Get storage resource configuration
                resource = await config_service.get_storage_resource(storage_path)

                # Create semaphore with configured limit
                limit = resource["io_limit"]
                self._io_semaphores[storage_path] = ResizableSemaphore(limit)
                self._semaphore_sizes[storage_path] = limit

            return self._io_semaphores[storage_path]

    def _get_storage_path(self, filepath: str) -> str:
        """Get the storage path for a file."""
        path = Path(filepath)
        # On Windows, return the drive letter
        if os.name == 'nt':
            return path.drive

        # On Unix, return the root directory as a fallback
        # A more robust implementation would determine the actual mount point
        return '/'

    async def resize_drive_semaphore(self, drive: str, new_limit: int) -> bool:
        """
        Resize the semaphore for a specific drive.

        Args:
            drive: Drive identifier
            new_limit: New concurrent IO limit

        Returns:
            True if resize was successful, False otherwise
        """
        if new_limit <= 0:
            return False

        # Update storage resource configuration
        success = await config_service.update_storage_resource(drive, new_limit)
        if not success:
            return False

        # Resize the existing semaphore if it exists
        with self._io_semaphores_lock:
            if drive in self._io_semaphores:
                self._io_semaphores[drive].resize(new_limit)
                self._semaphore_sizes[drive] = new_limit

        return True

    async def resize_process_pool(self, new_size: int) -> bool:
        """
        Resize the process pool to a new worker count.

        Creates a new pool immediately for new tasks, while existing
        tasks complete in the old pool.

        Args:
            new_size: New maximum number of workers

        Returns:
            True if resize was successfully initiated, False if invalid size
        """
        if new_size <= 0:
            return False

        # Update configuration
        await config_service.set("process_pool_size", new_size)
        self._process_pool_size = new_size

        with self._cpu_pool_lock:
            # Store old pool for cleanup
            old_pool = self._cpu_pool

            # Create new pool immediately
            if os.environ.get('PYTEST_CURRENT_TEST'):
                self._cpu_pool = concurrent.futures.ThreadPoolExecutor(
                    max_workers=new_size
                )
            else:
                self._cpu_pool = concurrent.futures.ProcessPoolExecutor(
                    max_workers=new_size
                )

            # Set old pool for cleanup when tasks complete
            self._old_pool = old_pool
            self._resize_pending = True

        return True

    def _check_shutdown_old_pool(self) -> None:
        """Check if we should shutdown the old pool."""
        if self._resize_pending and self._old_pool is not None and len(self._active_cpu_tasks) == 0:
            # No active tasks remaining, safe to shut down old pool
            self._old_pool.shutdown(wait=False)
            self._old_pool = None
            self._resize_pending = False

    async def submit_cpu_task(self, func: Callable[..., R], *args, **kwargs) -> R:
        """Submit a CPU-bound task to the process pool with metrics."""
        operation_name = func.__name__
        task_id = id(func) + id(tuple(args)) + id(str(kwargs))

        # Track this task
        with self._cpu_task_lock:
            self._active_cpu_tasks.add(task_id)
            self._check_shutdown_old_pool()  # Check if we can shut down old pool

        async def execution_func():
            try:
                # Execute the task using current pool (which is the new pool if resized)
                with self._cpu_pool_lock:
                    current_pool = self._cpu_pool

                loop = asyncio.get_event_loop()
                future = current_pool.submit(func, *args, **kwargs)
                result = await loop.run_in_executor(None, future.result)

                # Task completed, check if we can shut down old pool
                with self._cpu_task_lock:
                    self._active_cpu_tasks.remove(task_id)
                    self._check_shutdown_old_pool()

                return result
            except Exception as e:
                # Clean up tracking on error
                with self._cpu_task_lock:
                    if task_id in self._active_cpu_tasks:
                        self._active_cpu_tasks.remove(task_id)
                    self._check_shutdown_old_pool()
                raise e

        return await self.execute_with_metrics(
            resource_type="CPU",
            operation_name=operation_name,
            execution_func=execution_func
        )

    def shutdown(self):
        """Clean up resources."""
        if hasattr(self, '_cpu_pool') and self._cpu_pool:
            self._cpu_pool.shutdown()

    async def execute_with_metrics(self,
                                   resource_type: str,
                                   operation_name: str,
                                   execution_func: Callable[[], R],
                                   acquire_func: Optional[Callable[[], Any]] = None,
                                   release_func: Optional[Callable[[], None]] = None) -> R:
        """
        Execute a task with metrics tracking.
        """
        metrics = ExecutionMetrics(operation_name, resource_type, self.metrics_collector)
        metrics.mark_queued()

        acquired = False
        try:
            # Acquire resource if needed
            if acquire_func:
                await asyncio.get_event_loop().run_in_executor(None, acquire_func)
                acquired = True

            metrics.mark_started()

            # Execute the task
            result = await execution_func()

            metrics.mark_completed()
            return result

        finally:
            if acquired and release_func:
                release_func()

    async def submit_io_task(self, filepath: str, func: Callable[..., R], *args, **kwargs) -> R:
        """Submit an IO-bound task with semaphore control and metrics."""
        operation_name = func.__name__
        semaphore = await self.get_io_semaphore(filepath)

        def acquire_func():
            return semaphore.acquire()

        def release_func():
            semaphore.release()

        async def execution_func():
            # Check if the function is a coroutine function
            if asyncio.iscoroutinefunction(func):
                # Call async function directly
                return await func(*args, **kwargs)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

        return await self.execute_with_metrics(
            resource_type="IO",
            operation_name=operation_name,
            execution_func=execution_func,
            acquire_func=acquire_func,
            release_func=release_func
        )

    async def get_io_limits(self) -> Dict[str, Dict[str, Any]]:
        """Get current IO limits for all configured storage resources."""
        resources = await config_service.get("storage_resources", [])
        return {resource["path"]: resource for resource in resources}

    async def get_process_pool_size(self) -> int:
        """Get current process pool size configuration."""
        return await config_service.get("process_pool_size", self._process_pool_size)
