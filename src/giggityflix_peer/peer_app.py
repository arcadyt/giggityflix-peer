"""
Legacy peer_app module for backward compatibility.

Use the new peer_service module instead:
    from giggityflix_peer.peer_service import get_peer_service

This file exists only for compatibility with existing imports.
"""
import warnings
from giggityflix_peer.peer_service import get_peer_service

warnings.warn(
    "peer_app module is deprecated. Use peer_service instead.",
    DeprecationWarning,
    stacklevel=2
)

# Backward compatibility alias
peer_app = get_peer_service()
