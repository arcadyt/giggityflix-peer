"""Domain interfaces for drive detection."""
from typing import List, Optional, Protocol

from giggityflix_mgmt_peer.apps.drive_detection.domain.models import PhysicalDrive, DriveMapping


class DriveRepositoryInterface(Protocol):
    """Interface for drive repository."""

    def get_all_drives(self) -> List[PhysicalDrive]:
        """
        Get all drives from the storage.
        
        Returns:
            List of domain drive models
        """
        ...

    def get_drive_by_id(self, drive_id: str) -> Optional[PhysicalDrive]:
        """
        Get a drive by ID.
        
        Args:
            drive_id: Drive ID to look up
            
        Returns:
            Domain drive model or None if not found
        """
        ...

    def get_drive_mapping(self) -> DriveMapping:
        """
        Get a complete drive mapping from storage.
        
        Returns:
            DriveMapping with all drives and their partitions
        """
        ...

    def save_drive(self, drive: PhysicalDrive) -> str:
        """
        Save or update a drive.
        
        Args:
            drive: Domain drive model to save
            
        Returns:
            The ID of the saved drive
        """
        ...

    def save_drive_mapping(self, drive_mapping: DriveMapping) -> None:
        """
        Save a complete drive mapping.
        
        Args:
            drive_mapping: DriveMapping with drives and partitions to save
        """
        ...

    def clear_all_drives(self) -> None:
        """Remove all drives and partitions from storage."""
        ...
