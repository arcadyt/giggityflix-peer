import asyncio
import functools
import inspect
import threading
from typing import Any, Callable, TypeVar, Union, Tuple

R = TypeVar('R')

# Registry to track decorated methods
io_bound_registry = set()
cpu_bound_registry = set()


def get_resource_manager():
    """Get the resource manager from the DI container."""
    from giggityflix_peer.di import container
    from .resource_pool import ResourcePoolManager
    return container.resolve(ResourcePoolManager)


def io_bound(param_name='file_path'):
    """
    Decorator for IO-bound operations.

    Args:
        param_name: Name of the parameter containing the file_path
    """

    def decorator(func):
        # Register this function as IO-bound
        io_bound_registry.add(func)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            resource_manager = get_resource_manager()

            # Extract file_path
            if param_name in kwargs:
                file_path = kwargs[param_name]
            else:
                # Find the position of the file_path parameter
                sig = inspect.signature(func)
                param_names = list(sig.parameters.keys())
                if param_name in param_names:
                    idx = param_names.index(param_name)
                    if idx < len(args):
                        file_path = args[idx]
                    else:
                        raise ValueError(f"Missing required '{param_name}' parameter")
                else:
                    raise ValueError(f"Parameter '{param_name}' not found in function signature")

            return await resource_manager.submit_io_task(file_path, func, *args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                # Try to get the current event loop
                loop = asyncio.get_event_loop()

                # Check if the loop is already running
                if loop.is_running():
                    # We're in an async context, create a task in the existing loop
                    return asyncio.ensure_future(async_wrapper(*args, **kwargs))
                else:
                    # We're in a sync context, run the coroutine until complete
                    return loop.run_until_complete(async_wrapper(*args, **kwargs))
            except RuntimeError:
                # No event loop exists, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(async_wrapper(*args, **kwargs))
                finally:
                    loop.close()

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def cpu_bound():
    """Decorator for CPU-bound operations."""

    def decorator(func):
        # Register this function as CPU-bound
        cpu_bound_registry.add(func)

        # Thread-local storage to track if we're already inside an executor
        local = threading.local()

        # Create a non-decorated version of the function for use inside the executor
        @functools.wraps(func)
        def direct_impl(*args, **kwargs):
            return func(*args, **kwargs)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Check if we're already inside the executor
            inside_executor = getattr(local, 'inside_executor', False)
            if inside_executor:
                # We're inside the executor - run directly to avoid recursive submission
                return direct_impl(*args, **kwargs)

            # We're not in the executor, so submit the task
            resource_manager = get_resource_manager()

            # Create a synchronous function to run inside the executor
            def executor_run(*exec_args, **exec_kwargs):
                # Set flag that we're inside the executor
                local.inside_executor = True
                try:
                    # Run the original function directly
                    return direct_impl(*exec_args, **exec_kwargs)
                finally:
                    # Clear the flag
                    local.inside_executor = False

            # Submit the synchronous function to the CPU pool
            return await resource_manager.submit_cpu_task(executor_run, *args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Check if we're already inside the executor
            inside_executor = getattr(local, 'inside_executor', False)
            if inside_executor:
                # We're inside the executor - run directly to avoid recursive submission
                return direct_impl(*args, **kwargs)

            try:
                # Try to get the current event loop
                loop = asyncio.get_event_loop()

                # Check if the loop is already running
                if loop.is_running():
                    # We're in an async context, create a task in the existing loop
                    return asyncio.ensure_future(async_wrapper(*args, **kwargs))
                else:
                    # We're in a sync context, run the coroutine until complete
                    return loop.run_until_complete(async_wrapper(*args, **kwargs))
            except RuntimeError:
                # No event loop exists, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    return loop.run_until_complete(async_wrapper(*args, **kwargs))
                finally:
                    loop.close()

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


Task = Union[Callable[[], Any], Tuple[Callable, tuple, dict]]


async def execute_parallel(*tasks: Task):
    """
    Execute multiple tasks in parallel.

    Args:
        tasks: Either callable coroutines or tuples of (func, args, kwargs)

    Returns:
        List of results in the same order as the tasks
    """
    resource_manager = get_resource_manager()
    futures = []

    for task in tasks:
        if callable(task):
            # Handle CPU-bound decorated functions differently
            if task in cpu_bound_registry:
                # For CPU-bound tasks, submit directly to resource manager
                future = resource_manager.submit_cpu_task(task)
            else:
                # For regular async functions, just await them
                future = task()
            futures.append(future)
        elif isinstance(task, tuple) and len(task) >= 1 and callable(task[0]):
            # If it's a tuple of (func, args, kwargs)
            func = task[0]
            args = task[1] if len(task) > 1 else ()
            kwargs = task[2] if len(task) > 2 else {}

            # Handle CPU-bound decorated functions differently
            if func in cpu_bound_registry:
                # For CPU-bound tasks, submit directly to resource manager
                future = resource_manager.submit_cpu_task(func, *args, **kwargs)
            else:
                # For regular async functions, just await them
                future = func(*args, **kwargs)
            futures.append(future)
        else:
            raise TypeError(f"Expected a callable or tuple of (func, args, kwargs), got {type(task)}")

    return await asyncio.gather(*futures)