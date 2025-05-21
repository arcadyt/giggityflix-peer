"""Utilities for parallel execution."""
import asyncio
from concurrent.futures import Future
from typing import Any, Awaitable, Callable, List, Tuple, Union

from giggityflix_mgmt_peer.core.resource_pool.manager import get_resource_pool_manager

Task = Union[Awaitable[Any], Tuple[Callable[..., Any], Tuple, dict]]


async def execute_parallel(*tasks: Task) -> List[Any]:
    """
    Execute multiple tasks in parallel.
    
    Args:
        *tasks: Tasks to execute.
            - Awaitable: Will be awaited directly
            - (func, args, kwargs): Will be executed with the given arguments
    
    Returns:
        List of results in the order of the tasks
    """
    results = []

    # Convert all tasks to awaitables
    aws = []
    for task in tasks:
        if isinstance(task, tuple) and len(task) == 3 and callable(task[0]):
            # (func, args, kwargs) format
            func, args, kwargs = task
            aws.append(_execute_func(func, args, kwargs))
        else:
            # Awaitable
            aws.append(task)

    # Execute all tasks in parallel
    for result in await asyncio.gather(*aws, return_exceptions=True):
        if isinstance(result, Exception):
            # Re-raise exceptions
            raise result
        results.append(result)

    return results


async def _execute_func(func: Callable[..., Any], args: Tuple, kwargs: dict) -> Any:
    """
    Execute a function with the given arguments.
    
    If the function is CPU-bound, uses process pool.
    Otherwise uses thread pool.
    
    Args:
        func: Function to execute
        args: Positional arguments
        kwargs: Keyword arguments
    
    Returns:
        Function result
    """
    # Determine if function is CPU or IO bound
    # This is a simplified approach - ideally we would inspect decorators
    is_cpu_bound = hasattr(func, '_cpu_bound')

    # Get appropriate pool
    if is_cpu_bound:
        pool = get_resource_pool_manager().get_process_pool()
    else:
        pool = get_resource_pool_manager().get_thread_pool()

    # Submit to pool and get future
    future = pool.submit(func, *args, **kwargs)

    # Convert future to awaitable
    return await _future_to_awaitable(future)


async def _future_to_awaitable(future: Future) -> Any:
    """
    Convert a concurrent.futures.Future to an awaitable.
    
    Args:
        future: Future to convert
    
    Returns:
        Future result
    
    Raises:
        Exception: If the future raises an exception
    """
    loop = asyncio.get_event_loop()

    # Create event for signaling completion
    done_event = asyncio.Event()

    # Callback to set event when future completes
    def _on_future_done(fut):
        loop.call_soon_threadsafe(done_event.set)

    future.add_done_callback(_on_future_done)

    # Wait for future to complete
    await done_event.wait()

    # Get result or raise exception
    return future.result()
