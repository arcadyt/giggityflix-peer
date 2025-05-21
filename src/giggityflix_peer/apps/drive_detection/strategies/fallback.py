"""Fallback drive detection for unsupported platforms."""
import logging
import os
from typing import Dict, List

from giggityflix_mgmt_peer.apps.drive_detection.detection import DriveDetector
from giggityflix_mgmt_peer.apps.drive_detection.strategies.utils import extract_manufacturer, format_drive_data, \
    format_partition_data

logger = logging.getLogger(__name__)


class FallbackDriveDetector(DriveDetector):
    """Fallback detector for unsupported platforms."""

    def detect_drives(self) -> Dict[str, List]:
        """
        Provide a basic fallback detection that works on most platforms.
        Usually just detects the root directory.

        Returns:
            Dict with 'drives' and 'partitions' lists
        """
        logger.info("Using generic fallback detector")
        drives = []
        partitions = []

        # Add the current directory as a drive
        cwd = os.getcwd()
        drive_id = "fallback_0"
        drive_model = f"Directory_{os.path.basename(cwd)}"
        manufacturer = extract_manufacturer(drive_model, "Unknown")

        drive = format_drive_data(
            drive_id=drive_id,
            manufacturer=manufacturer,
            model=drive_model,
            size_bytes=0  # Size unknown
        )

        drives.append(drive)

        partition = format_partition_data(
            mount_point=cwd,
            physical_drive_id=drive_id
        )

        partitions.append(partition)

        logger.info(f"Added fallback drive: {drive_id}")
        logger.info(f"Added fallback partition: {cwd} -> {drive_id}")

        return {
            "drives": drives,
            "partitions": partitions
        }
