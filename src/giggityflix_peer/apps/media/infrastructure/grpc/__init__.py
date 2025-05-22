"""gRPC infrastructure for media communication."""

from .client import MediaGrpcClient
from .handlers import MediaGrpcHandlers

__all__ = ["MediaGrpcClient", "MediaGrpcHandlers"]
