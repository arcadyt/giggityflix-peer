"""
Drive detection models for backwards compatibility.

This file re-exports the ORM models from the infrastructure layer
to maintain backwards compatibility.
"""

from giggityflix_mgmt_peer.apps.drive_detection.infrastructure.orm import PhysicalDrive, Partition

__all__ = ['PhysicalDrive', 'Partition']
