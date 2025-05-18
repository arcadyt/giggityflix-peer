import functools
import inspect
from typing import Any, Callable, Dict, Type, get_type_hints


class Container:
    """A dependency injection container."""

    def __init__(self):
        self._services: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable[[], Any]] = {}

    def register(self, interface_type: Type, implementation_instance: Any):
        """Register a service instance."""
        self._services[interface_type] = implementation_instance

    def register_factory(self, interface_type: Type, factory: Callable[[], Any]):
        """Register a factory function to create service instances."""
        self._factories[interface_type] = factory

    def resolve(self, interface_type: Type) -> Any:
        """Resolve a service by its interface type."""
        if interface_type in self._services:
            return self._services[interface_type]

        if interface_type in self._factories:
            return self._factories[interface_type]()

        raise KeyError(f"No registration found for {interface_type.__name__}")

    def inject(self, func: Callable) -> Callable:
        """Decorator to inject dependencies based on type hints."""
        sig = inspect.signature(func)
        type_hints = get_type_hints(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            injected_kwargs = {}

            for param_name, param in sig.parameters.items():
                if param_name in kwargs:
                    continue  # Skip explicitly provided arguments

                if param_name in type_hints:
                    param_type = type_hints[param_name]
                    try:
                        injected_kwargs[param_name] = self.resolve(param_type)
                    except KeyError:
                        pass  # If dependency can't be resolved, let Python handle it

            return func(*args, **{**injected_kwargs, **kwargs})

        return wrapper


# Global container instance
container = Container()
