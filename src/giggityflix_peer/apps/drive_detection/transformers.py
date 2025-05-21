from typing import List, Dict, Tuple, Optional

from giggityflix_mgmt_peer.apps.drive_detection.domain.models import DriveMapping
# Import domain models
from giggityflix_mgmt_peer.apps.drive_detection.domain.models import PhysicalDrive as DomainDrive
from giggityflix_mgmt_peer.apps.drive_detection.models import Partition as OrmPartition
# Import ORM models
from giggityflix_mgmt_peer.apps.drive_detection.models import PhysicalDrive as OrmDrive


def domain_to_orm_drive(domain_drive: DomainDrive) -> OrmDrive:
    """
    Transform a domain PhysicalDrive to an ORM PhysicalDrive.

    Args:
        domain_drive: Domain model instance

    Returns:
        ORM model instance (not saved to database)
    """
    return OrmDrive(
        id=domain_drive.id,
        manufacturer=domain_drive.manufacturer,
        model=domain_drive.model,
        serial=domain_drive.serial,
        size_bytes=domain_drive.size_bytes,
        filesystem_type=domain_drive.filesystem_type
    )


def orm_to_domain_drive(orm_drive: OrmDrive) -> DomainDrive:
    """
    Transform an ORM PhysicalDrive to a domain PhysicalDrive.

    Args:
        orm_drive: Django ORM model instance

    Returns:
        Domain model instance
    """
    return DomainDrive(
        id=orm_drive.id,
        manufacturer=orm_drive.manufacturer,
        model=orm_drive.model,
        serial=orm_drive.serial,
        size_bytes=orm_drive.size_bytes,
        filesystem_type=orm_drive.filesystem_type
    )


def drive_mapping_to_orm(drive_mapping: DriveMapping) -> Tuple[List[OrmDrive], Dict[str, List[str]]]:
    """
    Convert DriveMapping to a list of ORM drives and partition mappings.

    Args:
        drive_mapping: DriveMapping instance containing drives and their partitions

    Returns:
        Tuple of (list of ORM drives, dict mapping drive IDs to partition paths)
    """
    orm_drives = []
    partition_mappings = {}

    # Transform all drives
    for domain_drive in drive_mapping.get_all_physical_drives():
        orm_drive = domain_to_orm_drive(domain_drive)
        orm_drives.append(orm_drive)

        # Get partitions for this drive
        partition_paths = drive_mapping.get_partitions_for_drive(domain_drive.id)
        if partition_paths:
            partition_mappings[domain_drive.id] = partition_paths

    return orm_drives, partition_mappings


def orm_to_drive_mapping(orm_drives: List[OrmDrive], with_partitions: bool = True) -> DriveMapping:
    """
    Create a DriveMapping from ORM drive models and their partitions.

    Args:
        orm_drives: List of ORM PhysicalDrive instances
        with_partitions: Whether to include partition data

    Returns:
        Populated DriveMapping instance
    """
    drive_mapping = DriveMapping()

    # Add all drives to mapping
    for orm_drive in orm_drives:
        domain_drive = orm_to_domain_drive(orm_drive)
        drive_mapping.add_physical_drive(domain_drive)

        # Add partitions if requested
        if with_partitions:
            for partition in orm_drive.partitions.all():
                drive_mapping.add_partition_mapping(partition.mount_point, orm_drive.id)

    return drive_mapping


def persist_drive_mapping(drive_mapping: DriveMapping) -> None:
    """
    Persist a DriveMapping instance to the database.

    Args:
        drive_mapping: DriveMapping containing drives and partitions to save
    """
    # Transform and save all drives
    for domain_drive in drive_mapping.get_all_physical_drives():
        # Update or create the drive
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

        # Get all partitions for this drive and create/update them
        partition_paths = drive_mapping.get_partitions_for_drive(domain_drive.id)
        for mount_point in partition_paths:
            OrmPartition.objects.update_or_create(
                mount_point=mount_point,
                defaults={'physical_drive': orm_drive}
            )

        # Optional: Remove partitions that no longer exist
        existing_partitions = orm_drive.partitions.values_list('mount_point', flat=True)
        deleted_partitions = set(existing_partitions) - set(partition_paths)
        if deleted_partitions:
            OrmPartition.objects.filter(
                mount_point__in=deleted_partitions,
                physical_drive=orm_drive
            ).delete()


def get_domain_drive_by_id(drive_id: str) -> Optional[DomainDrive]:
    """
    Get a domain drive by ID from the database.

    Args:
        drive_id: The ID of the drive to fetch

    Returns:
        Domain drive model or None if not found
    """
    try:
        orm_drive = OrmDrive.objects.get(id=drive_id)
        return orm_to_domain_drive(orm_drive)
    except OrmDrive.DoesNotExist:
        return None
