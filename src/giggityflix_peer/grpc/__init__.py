"""
gRPC client and handlers for the Giggityflix peer service.
"""

from .client import EdgeClient
from .handlers import EdgeMessageHandler

__all__ = ["EdgeClient", "EdgeMessageHandler"]
