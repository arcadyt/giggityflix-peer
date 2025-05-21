from typing import List, Optional

from django.db import transaction

from giggityflix_mgmt_peer.apps.drive_detection.domain.models import DriveMapping
from giggityflix_mgmt_peer.apps.drive_detection.domain.models import PhysicalDrive as DomainDrive
from giggityflix_mgmt_peer.apps.drive_detection.infrastructure.orm import Partition as OrmPartition
from giggityflix_mgmt_peer.apps.drive_detection.infrastructure.orm import PhysicalDrive as OrmDrive
from giggityflix_mgmt_peer.apps.drive_detection.infrastructure.transformers import (
    domain_to_orm_drive, orm_to_domain_drive, orm_to_drive_mapping
)


class DriveRepository:
    """Repository for managing drive data persistence."""

    def get_all_drives(self) -> List[DomainDrive]:
        """
        Get all drives from the database.
        
        Returns:
            List of domain drive models
        """
        orm_drives = OrmDrive.objects.all()
        return [orm_to_domain_drive(drive) for drive in orm_drives]

    def get_drive_by_id(self, drive_id: str) -> Optional[DomainDrive]:
        """
        Get a drive by ID.
        
        Args:
            drive_id: Drive ID to look up
            
        Returns:
            Domain drive model or None if not found
        """
        try:
            orm_drive = OrmDrive.objects.get(id=drive_id)
            return orm_to_domain_drive(orm_drive)
        except OrmDrive.DoesNotExist:
            return None

    def get_drive_mapping(self) -> DriveMapping:
        """
        Get a complete drive mapping from the database.
        
        Returns:
            DriveMapping with all drives and their partitions
        """
        orm_drives = OrmDrive.objects.all().prefetch_related('partitions')
        return orm_to_drive_mapping(orm_drives)

    @transaction.atomic
    def save_drive(self, drive: DomainDrive) -> str:
        """
        Save or update a drive in the database.
        
        Args:
            drive: Domain drive model to save
            
        Returns:
            The ID of the saved drive
        """
        orm_drive = domain_to_orm_drive(drive)
        orm_drive.save()
        return orm_drive.id

    @transaction.atomic
    def save_drive_mapping(self, drive_mapping: DriveMapping) -> None:
        """
        Save a complete drive mapping to the database.
        
        Args:
            drive_mapping: DriveMapping with drives and partitions to save
        """
        # First, save all drives
        for domain_drive in drive_mapping.get_all_physical_drives():
            orm_drive, created = OrmDrive.objects.update_or_create(
                id=domain_drive.id,
                defaults={
                    'manufacturer': domain_drive.manufacturer,
                    'model': domain_drive.model,
                    'serial': domain_drive.serial,
                    'size_bytes': domain_drive.size_bytes,
                    'filesystem_type': domain_drive.filesystem_type
                }
            )

            # Get all partitions for this drive
            partition_paths = drive_mapping.get_partitions_for_drive(domain_drive.id)

            # Add or update partitions
            for mount_point in partition_paths:
                OrmPartition.objects.update_or_create(
                    mount_point=mount_point,
                    defaults={'physical_drive': orm_drive}
                )

            # Remove partitions that no longer exist
            existing_partitions = list(orm_drive.partitions.values_list('mount_point', flat=True))
            deleted_partitions = set(existing_partitions) - set(partition_paths)
            if deleted_partitions:
                OrmPartition.objects.filter(
                    mount_point__in=deleted_partitions,
                    physical_drive=orm_drive
                ).delete()

    @transaction.atomic
    def clear_all_drives(self) -> None:
        """Remove all drives and partitions from the database."""
        OrmPartition.objects.all().delete()
        OrmDrive.objects.all().delete()


# Singleton instance
_drive_repository = None


def get_drive_repository() -> DriveRepository:
    """
    Get or create the drive repository singleton.
    
    Returns:
        DriveRepository instance
    """
    global _drive_repository
    if _drive_repository is None:
        _drive_repository = DriveRepository()
    return _drive_repository
