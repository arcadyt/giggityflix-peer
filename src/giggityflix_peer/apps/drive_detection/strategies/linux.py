"""Linux-specific drive detection implementation."""
import json
import logging
import subprocess
from typing import Dict, List, Any

from giggityflix_mgmt_peer.apps.drive_detection import DriveDetector
from giggityflix_mgmt_peer.apps.drive_detection.strategies.utils import extract_manufacturer, format_drive_data, \
    format_partition_data

logger = logging.getLogger(__name__)


class LinuxDriveDetector(DriveDetector):
    """Drive detector implementation for Linux."""

    def detect_drives(self) -> Dict[str, List]:
        """
        Detect drives on Linux systems.

        Returns:
            Dict with 'drives' and 'partitions' lists
        """
        try:
            # Try using lsblk for detection
            result = self._detect_with_lsblk()
            if result["drives"]:
                return result
        except Exception as e:
            logger.error(f"lsblk detection failed: {e}")

        # Fall back to mount points if lsblk fails
        try:
            result = self._detect_with_proc_mounts()
            return result
        except Exception as e:
            logger.error(f"Mount point detection failed: {e}")

        # Last resort - add root filesystem
        return self._detect_fallback()

    def _detect_with_lsblk(self) -> Dict[str, List]:
        """Detect drives using lsblk command."""
        logger.info("Running lsblk for drive detection")
        drives = []
        partitions = []

        process = subprocess.run(
            ["lsblk", "-Jbo", "NAME,SIZE,TYPE,MOUNTPOINT,MODEL,SERIAL,FSTYPE"],
            capture_output=True, text=True, check=True
        )

        data = json.loads(process.stdout)

        for device in data.get("blockdevices", []):
            if device.get("type") == "disk":
                drive_id = device.get("name", "unknown")

                # Extract model and manufacturer
                model = device.get("model", "Unknown").strip()
                manufacturer = extract_manufacturer(model, "Unknown")

                drive = format_drive_data(
                    drive_id=drive_id,
                    manufacturer=manufacturer,
                    model=model,
                    serial=device.get("serial", "Unknown").strip(),
                    size_bytes=int(device.get("size", 0)),
                    filesystem_type=device.get("fstype", "Unknown").strip() or "Unknown"
                )

                drives.append(drive)
                logger.info(f"Found disk: {drive_id}")

                # Process partitions
                self._process_lsblk_partitions(device, drive_id, partitions)

        return {
            "drives": drives,
            "partitions": partitions
        }

    def _process_lsblk_partitions(self, device: Dict[str, Any], drive_id: str, partitions: List) -> None:
        """Process partitions from lsblk output."""
        for child in device.get("children", []):
            if child.get("mountpoint"):
                partition = format_partition_data(
                    mount_point=child.get("mountpoint"),
                    physical_drive_id=drive_id
                )
                partitions.append(partition)
                logger.info(f"Found partition: {child.get('mountpoint')} -> {drive_id}")

    def _detect_with_proc_mounts(self) -> Dict[str, List]:
        """Detect drives using /proc/mounts."""
        logger.info("Using /proc/mounts for drive detection")
        drives = []
        partitions = []

        with open("/proc/mounts", "r") as f:
            mounts = f.readlines()

        for i, line in enumerate(mounts):
            parts = line.split()
            if len(parts) >= 2 and parts[0].startswith('/'):
                device = parts[0]
                mount_point = parts[1]

                # Extract model and manufacturer
                drive_id = f"linux_{i}"
                mount_model = f"Mount_{mount_point.replace('/', '_')}"
                manufacturer = extract_manufacturer(mount_model, "Unknown")

                drive = format_drive_data(
                    drive_id=drive_id,
                    manufacturer=manufacturer,
                    model=mount_model,
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
