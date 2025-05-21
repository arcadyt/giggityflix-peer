from typing import Dict, List, Optional


class PhysicalDrive:
    """Model for detection representing a physical drive."""

    def __init__(
            self,
            id: str,
            manufacturer: str = "Unknown",
            model: str = "Unknown",
            serial: str = "Unknown",
            size_bytes: int = 0,
            filesystem_type: str = "Unknown"
    ):
        self.id = id
        self.manufacturer = manufacturer
        self.model = model
        self.serial = serial
        self.size_bytes = size_bytes
        self.filesystem_type = filesystem_type

    def __str__(self) -> str:
        return f"{self.id} - {self.model} ({self.size_bytes} bytes)"

    def get_drive_id(self) -> str:
        """Return a normalized drive ID."""
        return f"drive_{self.id}"

    def to_dict(self) -> Dict:
        """Convert to dictionary for debugging."""
        return {
            "id": self.id,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "size_bytes": self.size_bytes,
            "filesystem_type": self.filesystem_type
        }


class DriveMapping:
    """Maps partitions to physical drives."""

    def __init__(self):
        self._drives: Dict[str, PhysicalDrive] = {}
        self._partitions: Dict[str, str] = {}  # partition -> drive_id

    def add_physical_drive(self, drive: PhysicalDrive) -> None:
        """Add a physical drive to the mapping."""
        self._drives[drive.id] = drive

    def add_partition_mapping(self, partition: str, drive_id: str) -> None:
        """Add a mapping from partition to drive ID."""
        self._partitions[partition] = drive_id

    def get_physical_drive_for_partition(self, partition: str) -> Optional[PhysicalDrive]:
        """Get the physical drive for a partition."""
        drive_id = self._partitions.get(partition)
        if drive_id:
            return self._drives.get(drive_id)
        return None

    def get_all_physical_drives(self) -> List[PhysicalDrive]:
        """Get all physical drives."""
        return list(self._drives.values())

    def get_partitions_for_drive(self, drive_id: str) -> List[str]:
        """Get all partitions for a drive."""
        return [p for p, d in self._partitions.items() if d == drive_id]

    def to_dict(self) -> Dict:
        """Convert to dictionary for debugging."""
        return {
            "drives": {drive_id: drive.to_dict() for drive_id, drive in self._drives.items()},
            "partitions": self._partitions
        }
