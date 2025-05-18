import threading
import time


class ResizableSemaphore:
    """
    A semaphore implementation that allows dynamic resizing of the permit count.
    Used to control concurrent access to resource-limited operations.
    """

    def __init__(self, max_permits):
        if max_permits < 0:
            raise ValueError("Semaphore initial max permits must be non-negative")
        self._cond = threading.Condition()
        self._max_permits = max_permits
        self._available_permits = max_permits

    def acquire(self, blocking=True, timeout=None):
        """
        Acquire a permit from the semaphore.

        Args:
            blocking: If False, don't block if no permits are available
            timeout: Maximum time to wait for a permit

        Returns:
            True if a permit was acquired, False otherwise
        """
        with self._cond:
            if not blocking:
                if self._available_permits > 0:
                    self._available_permits -= 1
                    return True
                else:
                    return False

            # Handle blocking case
            if timeout is not None:
                end_time = time.time() + timeout
                while self._available_permits <= 0:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        return False
                    if not self._cond.wait(remaining):
                        return False
                self._available_permits -= 1
                return True
            else:
                # Handle blocking with no timeout (wait until acquired)
                while self._available_permits <= 0:
                    self._cond.wait()
                self._available_permits -= 1
                return True

    def release(self):
        """
        Release a permit back to the semaphore.
        """
        with self._cond:
            if self._available_permits < self._max_permits:
                self._available_permits += 1
                self._cond.notify()

    def resize(self, new_max):
        """
        Resize the semaphore to a new maximum number of permits.

        Args:
            new_max: New maximum permit count

        Raises:
            ValueError: If new_max is negative
        """
        if new_max < 0:
            raise ValueError("Semaphore max permits cannot be negative")
        with self._cond:
            old_max = self._max_permits
            self._max_permits = new_max

            # If decreasing limit, cap available permits
            if new_max < self._available_permits:
                self._available_permits = new_max

            # Notify all waiting threads
            self._cond.notify_all()

    @property
    def max_permits(self):
        """Get the maximum number of permits."""
        return self._max_permits

    @property
    def available_permits(self):
        """Get the current number of available permits."""
        return self._available_permits
