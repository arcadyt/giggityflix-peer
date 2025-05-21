"""Windows-specific drive detection implementation."""
import ctypes
import logging
import os
import string
from typing import Dict, List

from giggityflix_mgmt_peer.apps.drive_detection import DriveDetector
from giggityflix_mgmt_peer.apps.drive_detection.strategies.utils import clean_string, extract_manufacturer, \
    extract_disk_number
from giggityflix_mgmt_peer.apps.drive_detection.strategies.utils import format_drive_data, format_partition_data

logger = logging.getLogger(__name__)


class WindowsDriveDetector(DriveDetector):
    """Drive detector implementation for Windows."""

    def detect_drives(self) -> Dict[str, List]:
        """
        Detect drives on Windows systems.

        Returns:
            Dict with 'drives' and 'partitions' lists
        """
        try:
            # Try WMI detection first if available
            if self._is_wmi_available():
                logger.info("Using WMI for Windows drive detection")

                # Initialize COM
                import pythoncom
                pythoncom.CoInitialize()

                try:
                    result = self._detect_with_wmi()
                finally:
                    pythoncom.CoUninitialize()

                return result
        except Exception as e:
            logger.error(f"WMI detection failed: {e}")

        # Fall back to simple detection if WMI fails
        logger.info("Using fallback method for Windows drive detection")
        return self._detect_fallback()

    def _is_wmi_available(self) -> bool:
        """Check if WMI is available."""
        try:
            import wmi
            return True
        except ImportError:
            return False

    def _detect_with_wmi(self) -> Dict[str, List]:
        """Detect drives using WMI."""
        import wmi
        drives = []
        partitions = []
        c = wmi.WMI()

        # First get all physical disks
        for physical_disk in c.Win32_DiskDrive():
            drive_id = str(physical_disk.Index)

            # Collect drive info
            raw_manufacturer = clean_string(physical_disk.Manufacturer)
            model = clean_string(physical_disk.Model)

            # Extract actual manufacturer from model if needed
            manufacturer = extract_manufacturer(model, raw_manufacturer)

            drive = format_drive_data(
                drive_id=drive_id,
                manufacturer=manufacturer,
                model=model,
                serial=clean_string(physical_disk.SerialNumber),
                size_bytes=int(physical_disk.Size) if physical_disk.Size else 0,
                filesystem_type="Unknown"  # Will be updated later
            )

            # Add to drives list
            drives.append(drive)
            logger.info(f"Found physical drive: {drive['id']} - {drive['manufacturer']} {drive['model']}")

        # Map partitions to physical drives
        self._map_partitions_wmi(c, drives, partitions)

        return {
            "drives": drives,
            "partitions": partitions
        }

    def _map_partitions_wmi(self, wmi_connection, drives, partitions):
        """Map logical drives to physical drives using WMI."""
        drive_map = {drive["id"]: drive for drive in drives}

        for partition in wmi_connection.Win32_DiskPartition():
            disk_id = extract_disk_number(partition.DeviceID)
            if disk_id is None:
                logger.warning(f"Couldn't extract disk ID from {partition.DeviceID}")
                continue

            # Map logical disks (drive letters) to this partition
            for logical_disk_mapping in wmi_connection.Win32_LogicalDiskToPartition():
                try:
                    # Get Antecedent DeviceID safely
                    partition_deviceid = self._get_wmi_property(
                        logical_disk_mapping, 'Antecedent', 'DeviceID')

                    if partition_deviceid and partition.DeviceID in partition_deviceid:
                        # Get drive letter safely
                        logical_deviceid = self._get_wmi_property(
                            logical_disk_mapping, 'Dependent', 'DeviceID')

                        if logical_deviceid:
                            # Add partition mapping
                            partition_entry = format_partition_data(
                                mount_point=logical_deviceid,
                                physical_drive_id=disk_id
                            )
                            partitions.append(partition_entry)
                            logger.info(f"Mapped {logical_deviceid} to physical drive {disk_id}")

                            # Update filesystem type in the corresponding drive
                            self._update_filesystem_type_wmi(
                                wmi_connection, logical_deviceid, disk_id, drive_map)
                except Exception as e:
                    logger.warning(f"Error processing partition mapping: {e}")

    def _get_wmi_property(self, obj, prop_path, final_prop):
        """Safely get a nested WMI property."""
        try:
            if hasattr(obj, prop_path):
                nested_obj = getattr(obj, prop_path)
                if hasattr(nested_obj, final_prop):
                    return getattr(nested_obj, final_prop)
        except Exception:
            pass
        return None

    def _update_filesystem_type_wmi(self, wmi_connection, logical_deviceid, disk_id, drive_map):
        """Update the filesystem type for a drive based on logical disk info."""
        for logical_disk in wmi_connection.Win32_LogicalDisk():
            if logical_disk.DeviceID == logical_deviceid and logical_disk.FileSystem:
                fs_type = logical_disk.FileSystem
                # Update the drive if we found it
                if disk_id in drive_map and drive_map[disk_id]["filesystem_type"] == "Unknown":
                    drive_map[disk_id]["filesystem_type"] = fs_type
                    logger.info(f"Found filesystem type: {fs_type} for drive {disk_id}")

    def _detect_fallback(self) -> Dict[str, List]:
        """Fallback drive detection using drive letters and Win32 APIs."""
        drives = []
        partitions = []

        # Use simple drive letter detection
        for letter in string.ascii_uppercase:
            drive_letter = f"{letter}:"
            if os.path.exists(drive_letter):
                try:
                    # Get drive info using Win32 API
                    drive_info = self._get_drive_info(drive_letter)
                    drive_id = f"win_{letter.lower()}"

                    model = drive_info.get("label") or f"Drive_{letter}"
                    manufacturer = extract_manufacturer(model, "Unknown")

                    drive = format_drive_data(
                        drive_id=drive_id,
                        manufacturer=manufacturer,
                        model=model,
                        serial=drive_info.get("serial", "Unknown"),
                        size_bytes=drive_info.get("size", 0),
                        filesystem_type=drive_info.get("filesystem", "Unknown")
                    )

                    drives.append(drive)
                    logger.info(f"Added drive: {drive['id']} - {drive['manufacturer']} {drive['model']}")

                    # Add partition mapping
                    partition = format_partition_data(
                        mount_point=drive_letter,
                        physical_drive_id=drive_id
                    )

                    partitions.append(partition)
                    logger.info(f"Added partition: {drive_letter} -> {drive_id}")

                except Exception as e:
                    logger.error(f"Error processing drive {drive_letter}: {e}")

                    # Create minimal entries
                    drive_id = f"win_{letter.lower()}"
                    drives.append(format_drive_data(
                        drive_id=drive_id,
                        manufacturer="Unknown",
                        model=f"Drive_{letter}",
                        size_bytes=0
                    ))

                    partitions.append(format_partition_data(
                        mount_point=drive_letter,
                        physical_drive_id=drive_id
                    ))

        return {
            "drives": drives,
            "partitions": partitions
        }

    def _get_drive_info(self, drive_letter: str) -> Dict:
        """Get drive information using Win32 API."""
        result = {
            "label": "",
            "serial": "",
            "filesystem": "Unknown",
            "size": 0
        }

        try:
            # Use GetVolumeInformation
            kernel32 = ctypes.windll.kernel32
            volume_name_buffer = ctypes.create_unicode_buffer(1024)
            volume_serial = ctypes.c_ulong(0)
            max_component_length = ctypes.c_ulong(0)
            file_system_flags = ctypes.c_ulong(0)
            file_system_name_buffer = ctypes.create_unicode_buffer(1024)

            if kernel32.GetVolumeInformationW(
                    ctypes.c_wchar_p(f"{drive_letter}\\"),
                    volume_name_buffer,
                    1024,
                    ctypes.byref(volume_serial),
                    ctypes.byref(max_component_length),
                    ctypes.byref(file_system_flags),
                    file_system_name_buffer,
                    1024
            ):
                result["label"] = volume_name_buffer.value
                result["serial"] = str(volume_serial.value)
                result["filesystem"] = file_system_name_buffer.value

            # Get drive size
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            total_free_bytes = ctypes.c_ulonglong(0)

            if kernel32.GetDiskFreeSpaceExW(
                    ctypes.c_wchar_p(f"{drive_letter}\\"),
                    ctypes.byref(free_bytes),
                    ctypes.byref(total_bytes),
                    ctypes.byref(total_free_bytes)
            ):
                result["size"] = total_bytes.value

        except Exception as e:
            logger.error(f"Error in GetVolumeInformation: {e}")

        return result
