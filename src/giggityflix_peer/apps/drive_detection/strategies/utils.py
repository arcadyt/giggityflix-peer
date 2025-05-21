"""Utility functions for drive detection."""
import logging
import re
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def clean_string(value: Optional[str]) -> str:
    """Clean and normalize a string value."""
    if not value:
        return "Unknown"

    # Replace spaces and special characters
    cleaned = re.sub(r'[^\w]', '_', value.strip())
    # Remove multiple underscores
    cleaned = re.sub(r'_+', '_', cleaned)
    # Remove trailing underscores
    cleaned = cleaned.strip('_')

    return cleaned or "Unknown"


def extract_manufacturer(model: str, raw_manufacturer: str) -> str:
    """Extract the actual manufacturer from model string if raw_manufacturer is generic."""
    # If raw manufacturer is not generic, use it
    if raw_manufacturer and raw_manufacturer.lower() not in ["standard_disk_drives", "unknown", "standard", "generic"]:
        return raw_manufacturer

    # Try to extract manufacturer from model string
    if not model or model.lower() in ["unknown"]:
        return "Unknown"

    # Common patterns for extracting manufacturer from model
    patterns = [
        # Pattern 1: Manufacturer_Product format (e.g., "SAMSUNG_MZVL2")
        r'^([A-Za-z0-9]+)_',
        # Pattern 2: Manufacturer Product format with space (e.g., "SAMSUNG MZVL2")
        r'^([A-Za-z0-9]+)\s',
        # Pattern 3: ManufacturerProduct format where manufacturer name is all caps
        r'^([A-Z]+)(?=[A-Z][a-z]|[0-9])',
    ]

    # Try each pattern in order
    for pattern in patterns:
        match = re.search(pattern, model)
        if match:
            manufacturer = match.group(1)
            # Properly capitalize (first letter upper, rest lower)
            manufacturer = manufacturer.strip().lower()
            manufacturer = manufacturer[0].upper() + manufacturer[1:]
            return manufacturer

    # If no pattern matches, return the first segment before any separator
    parts = re.split(r'[_\s-]+', model.strip(), 1)
    if len(parts) > 0 and parts[0]:
        # Clean up the manufacturer name
        manufacturer = parts[0].strip().lower()
        manufacturer = manufacturer[0].upper() + manufacturer[1:]
        return manufacturer

    # Return raw manufacturer if we couldn't extract anything better
    return raw_manufacturer or "Unknown"


def extract_disk_number(partition_id: str) -> Optional[str]:
    """Extract disk number from partition device ID."""
    patterns = [
        r'Disk #(\d+),\s+Partition',  # Common format
        r'disk\s+#(\d+)',  # Alternative format (case insensitive)
        r'disk(\d+)',  # Simple format
    ]

    for pattern in patterns:
        match = re.search(pattern, partition_id, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def format_drive_data(drive_id: str, manufacturer: str, model: str,
                      serial: str = "Unknown", size_bytes: int = 0,
                      filesystem_type: str = "Unknown") -> Dict:
    """Format drive data into a standard dictionary."""
    return {
        "id": drive_id,
        "manufacturer": manufacturer,
        "model": model,
        "serial": serial,
        "size_bytes": size_bytes,
        "filesystem_type": filesystem_type
    }


def format_partition_data(mount_point: str, physical_drive_id: str) -> Dict:
    """Format partition data into a standard dictionary."""
    return {
        "mount_point": mount_point,
        "physical_drive_id": physical_drive_id
    }
