"""Drive detection utilities."""
from abc import ABC, abstractmethod
from typing import Dict, List


class DriveDetector(ABC):
    """Base interface for drive detection strategies."""

    @abstractmethod
    def detect_drives(self) -> Dict[str, List]:
        """
        Detect drives and partitions on the current system.

        Returns:
            Dict with 'drives' and 'partitions' lists
        """
        pass


class DriveDetectorFactory:
    """Factory for creating appropriate drive detector based on platform."""

    @staticmethod
    def create_detector() -> DriveDetector:
        """Create a drive detector for the current platform."""
        import platform
        system = platform.system()

        if system == "Windows":
            from giggityflix_mgmt_peer.apps.drive_detection.strategies.windows import WindowsDriveDetector
            return WindowsDriveDetector()
        elif system == "Linux":
            from giggityflix_mgmt_peer.apps.drive_detection.strategies.linux import LinuxDriveDetector
            return LinuxDriveDetector()
        elif system == "Darwin":
            from giggityflix_mgmt_peer.apps.drive_detection.strategies.macos import MacOSDriveDetector
            return MacOSDriveDetector()
        else:
            # Return a fallback detector for unsupported platforms
            from giggityflix_mgmt_peer.apps.drive_detection.strategies.fallback import FallbackDriveDetector
            return FallbackDriveDetector()
