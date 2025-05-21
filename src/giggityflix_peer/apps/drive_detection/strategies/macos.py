"""macOS-specific drive detection implementation."""
import logging
import os
import subprocess
from typing import Dict, List

from giggityflix_mgmt_peer.apps.drive_detection import DriveDetector
from giggityflix_mgmt_peer.apps.drive_detection.strategies.utils import extract_manufacturer, format_drive_data, \
    format_partition_data

logger = logging.getLogger(__name__)


class MacOSDriveDetector(DriveDetector):
    """Drive detector implementation for macOS."""

    def detect_drives(self) -> Dict[str, List]:
        """
        Detect drives on macOS systems.

        Returns:
            Dict with 'drives' and 'partitions' lists
        """
        try:
            # Try using diskutil for detection
            result = self._detect_with_diskutil()
            if result["drives"]:
                return result
        except Exception as e:
            logger.error(f"diskutil detection failed: {e}")

        # Fall back to mount command if diskutil fails
        try:
            result = self._detect_with_mount()
            return result
        except Exception as e:
            logger.error(f"Mount command detection failed: {e}")

        # Last resort - add root filesystem
        return self._detect_fallback()

    def _detect_with_diskutil(self) -> Dict[str, List]:
        """Detect drives using diskutil command."""
        logger.info("Running diskutil for drive detection")
        drives = []
        partitions = []

        try:
            # Get list of disks
            process = subprocess.run(
                ["diskutil", "list", "-plist"],
                capture_output=True, text=True, check=True
            )

            import plistlib
            disks_data = plistlib.loads(process.stdout.encode('utf-8'))

            for disk_entry in disks_data.get("AllDisksAndPartitions", []):
                if "DeviceIdentifier" in disk_entry:
                    disk_id = disk_entry["DeviceIdentifier"]

                    # Get detailed info for this disk
                    self._process_diskutil_disk(disk_id, drives, partitions)
        except Exception as e:
            logger.error(f"Error processing diskutil list: {e}")
            raise

        return {
            "drives": drives,
            "partitions": partitions
        }

    def _process_diskutil_disk(self, disk_id: str, drives: List, partitions: List) -> None:
        """Process a single disk with diskutil info."""
        try:
            # Get disk info
            info_process = subprocess.run(
                ["diskutil", "info", "-plist", disk_id],
                capture_output=True, text=True, check=True
            )

            import plistlib
            info = plistlib.loads(info_process.stdout.encode('utf-8'))

            # Extract model and manufacturer
            model = info.get("DeviceModel", "Unknown") or "Unknown"
            manufacturer = extract_manufacturer(model, "Unknown")

            drive = format_drive_data(
                drive_id=disk_id,
                manufacturer=manufacturer,
                model=model,
                serial=info.get("IORegistryEntrySerial", "Unknown") or "Unknown",
                size_bytes=info.get("Size", 0),
                filesystem_type=info.get("FilesystemType", "Unknown") or "Unknown"
            )

            drives.append(drive)
            logger.info(f"Found disk: {disk_id} - {model}")

            # Add mount point if available
            if "MountPoint" in info and info["MountPoint"]:
                partition = format_partition_data(
                    mount_point=info["MountPoint"],
                    physical_drive_id=disk_id
                )
                partitions.append(partition)
                logger.info(f"Found mount point: {info['MountPoint']} -> {disk_id}")

            # Process partitions if available
            if "Partitions" in info:
                for part in info["Partitions"]:
                    if "MountPoint" in part and part["MountPoint"]:
                        part_id = part.get("DeviceIdentifier", disk_id)
                        partition = format_partition_data(
                            mount_point=part["MountPoint"],
                            physical_drive_id=disk_id
                        )
                        partitions.append(partition)
                        logger.info(f"Found partition: {part['MountPoint']} -> {disk_id}")

        except Exception as e:
            logger.error(f"Error processing disk {disk_id}: {e}")

    def _detect_with_mount(self) -> Dict[str, List]:
        """Detect drives using mount command."""
        logger.info("Using mount command for drive detection")
        drives = []
        partitions = []

        process = subprocess.run(
            ["mount"],
            capture_output=True, text=True, check=True
        )

        mount_lines = process.stdout.splitlines()

        for i, line in enumerate(mount_lines):
            parts = line.split(" on ")
            if len(parts) >= 2:
                device = parts[0]
                mount_parts = parts[1].split(" (")
                if len(mount_parts) >= 1:
                    mount_point = mount_parts[0]

                    # Extract model and manufacturer
                    drive_id = f"macos_{i}"
                    volume_model = f"Volume_{os.path.basename(mount_point)}"
                    manufacturer = extract_manufacturer(volume_model, "Unknown")

                    drive = format_drive_data(
                        drive_id=drive_id,
                        manufacturer=manufacturer,
                        model=volume_model,
                        size_bytes=0  # Size unknown
                    )

                    drives.append(drive)
                    logger.info(f"Added drive from mount: {drive_id}")

                    partition = format_partition_data(
                        mount_point=mount_point,
                        physical_drive_id=drive_id
                    )

                    partitions.append(partition)
                    logger.info(f"Added partition from mount: {mount_point} -> {drive_id}")

        return {
            "drives": drives,
            "partitions": partitions
        }

    def _detect_fallback(self) -> Dict[str, List]:
        """Fallback to add just the root filesystem."""
        logger.info("Using fallback detection (root filesystem only)")
        root_model = "Root_Volume"
        manufacturer = extract_manufacturer(root_model, "Unknown")

        drive = format_drive_data(
            drive_id="root",
            manufacturer=manufacturer,
            model=root_model,
            size_bytes=0
        )

        partition = format_partition_data(
            mount_point="/",
            physical_drive_id="root"
        )

        return {
            "drives": [drive],
            "partitions": [partition]
        }
