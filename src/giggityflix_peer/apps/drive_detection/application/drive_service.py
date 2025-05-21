"""Application service for drive detection."""
import logging
from typing import Dict, List

from giggityflix_mgmt_peer.apps.drive_detection.detection import DriveDetectorFactory
from giggityflix_mgmt_peer.apps.drive_detection.domain.interfaces import DriveRepositoryInterface
from giggityflix_mgmt_peer.apps.drive_detection.domain.models import DriveMapping, PhysicalDrive

# Set up logging
logger = logging.getLogger(__name__)


class DriveApplicationService:
    """Application service for detecting and managing drives."""

    def __init__(self, drive_repository: DriveRepositoryInterface):
        """
        Initialize the drive service with its dependencies.
        
        Args:
            drive_repository: Repository for drive persistence
        """
        self.drive_repository = drive_repository

    def detect_and_persist_drives(self) -> Dict[str, int]:
        """
        Detect all drives and partitions and persist them to the database.
        Returns a summary of changes.
        """
        # Clear existing data
        logger.info("Clearing existing drive data...")
        self.drive_repository.clear_all_drives()

        # Detect drives using the appropriate detector
        logger.info("Detecting drives...")
        detector = DriveDetectorFactory.create_detector()
        result = detector.detect_drives()

        drives_data = result.get("drives", [])
        partitions_data = result.get("partitions", [])

        logger.info(f"Found {len(drives_data)} drives and {len(partitions_data)} partitions")

        # Create a domain model representation
        drive_mapping = DriveMapping()

        # Add drives to the mapping
        for drive_data in drives_data:
            drive_id = drive_data['id']
            domain_drive = PhysicalDrive(
                id=drive_id,
                manufacturer=drive_data.get('manufacturer', 'Unknown'),
                model=drive_data.get('model', 'Unknown'),
                serial=drive_data.get('serial', 'Unknown'),
                size_bytes=drive_data.get('size_bytes', 0),
                filesystem_type=drive_data.get('filesystem_type', 'Unknown')
            )
            drive_mapping.add_physical_drive(domain_drive)

        # Add partitions to the mapping
        for partition_data in partitions_data:
            mount_point = partition_data['mount_point']
            physical_drive_id = partition_data.get('physical_drive_id')
            if physical_drive_id:
                drive_mapping.add_partition_mapping(mount_point, physical_drive_id)

        # Persist the domain model to the database using the repository
        self.drive_repository.save_drive_mapping(drive_mapping)

        return {
            "drives_added": len(drives_data),
            "partitions_added": len(partitions_data)
        }

    def get_all_drives(self) -> List[PhysicalDrive]:
        """
        Get all drives from the database.
        
        Returns:
            List of domain drive models
        """
        return self.drive_repository.get_all_drives()

    def get_drive_mapping(self) -> DriveMapping:
        """
        Get the complete drive mapping from the database.
        
        Returns:
            DriveMapping with all drives and their partitions
        """
        return self.drive_repository.get_drive_mapping()


# Singleton instance
_drive_service = None


def get_drive_service() -> DriveApplicationService:
    """
    Factory function to get or create the drive service singleton.
    
    Returns:
        DriveApplicationService instance
    """
    global _drive_service
    if _drive_service is None:
        from giggityflix_mgmt_peer.apps.drive_detection.infrastructure.repositories import get_drive_repository
        _drive_service = DriveApplicationService(get_drive_repository())
    return _drive_service
