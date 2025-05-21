"""
Giggityflix Management Peer service.

A resource management microservice with AOP capabilities for the Giggityflix
media streaming platform.
"""

from giggityflix_mgmt_peer.core.resource_pool import (
    ResourcePoolManager,
    io_bound,
    cpu_bound,
    execute_parallel
)

__version__ = "0.1.0"

__all__ = [
    'ResourcePoolManager',
    'io_bound',
    'cpu_bound',
    'execute_parallel',
]
