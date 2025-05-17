import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Optional

from giggityflix_peer.services.config_service import config_service, get_drive_info_for_path

logger = logging.getLogger(__name__)


class DiskIOService:
    """Service for managing disk I/O operations with concurrency limits."""

    def __init__(self):
        """Initialize the disk I/O service."""
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._physical_drive_mapping: Dict[str, str] = {}

    async def initialize(self) -> None:
        """Initialize the service with drive configurations."""
        # Load drive configurations
        drive_configs = await config_service.get_all_drive_configs()
        
        # Create semaphores based on configurations
        for drive_id, config in drive_configs.items():
            physical_drive = config["physical_drive"]
            concurrent_ops = config["concurrent_operations"]
            
            # Update physical drive mapping
            self._physical_drive_mapping[drive_id] = physical_drive
            
            # Create or update semaphore
            if physical_drive not in self._semaphores:
                self._semaphores[physical_drive] = asyncio.Semaphore(concurrent_ops)
            else:
                # If multiple logical drives map to the same physical drive,
                # use the highest concurrent operation limit
                existing_semaphore = self._semaphores[physical_drive]
                if existing_semaphore._value < concurrent_ops:
                    self._semaphores[physical_drive] = asyncio.Semaphore(concurrent_ops)
        
        logger.info(f"Initialized disk I/O service with {len(self._semaphores)} physical drives")

    async def get_physical_drive(self, path: str) -> str:
        """Get the physical drive for a path."""
        drive_id, physical_drive = get_drive_info_for_path(path)
        return physical_drive

    def get_semaphore(self, physical_drive: str) -> asyncio.Semaphore:
        """Get the semaphore for a physical drive."""
        if physical_drive not in self._semaphores:
            # Create a new semaphore with default limit (1)
            logger.info(f"Creating new semaphore for physical drive: {physical_drive}")
            self._semaphores[physical_drive] = asyncio.Semaphore(1)
        
        return self._semaphores[physical_drive]

    @asynccontextmanager
    async def operation(self, path_or_drive: str):
        """
        Context manager for a disk operation.
        
        Limits concurrent operations on the same physical drive.
        
        Args:
            path_or_drive: File path or drive ID
        """
        path_obj = Path(path_or_drive)
        
        # Determine physical drive
        if path_obj.exists() or "/" in path_or_drive or "\\" in path_or_drive:
            # It's a path
            _, physical_drive = get_drive_info_for_path(str(path_obj))
        elif path_or_drive in self._physical_drive_mapping:
            # It's a logical drive ID
            physical_drive = self._physical_drive_mapping[path_or_drive]
        else:
            # Assume it's a physical drive ID
            physical_drive = path_or_drive
        
        # Get the semaphore for this physical drive
        semaphore = self.get_semaphore(physical_drive)
        
        try:
            # Acquire the semaphore
            await semaphore.acquire()
            logger.debug(f"Acquired semaphore for {physical_drive}")
            
            yield
            
        finally:
            # Release the semaphore
            semaphore.release()
            logger.debug(f"Released semaphore for {physical_drive}")

    async def update_semaphore_limits(self) -> None:
        """Update semaphore limits based on current configurations."""
        # Get current drive configurations
        drive_configs = await config_service.get_all_drive_configs()
        
        # Track physical drives and their max concurrent operations
        physical_drive_limits = {}
        
        # Update physical drive mapping and collect limits
        for drive_id, config in drive_configs.items():
            physical_drive = config["physical_drive"]
            concurrent_ops = config["concurrent_operations"]
            
            # Update mapping
            self._physical_drive_mapping[drive_id] = physical_drive
            
            # Update max concurrent operations
            current_max = physical_drive_limits.get(physical_drive, 0)
            physical_drive_limits[physical_drive] = max(current_max, concurrent_ops)
        
        # Update semaphores
        for physical_drive, limit in physical_drive_limits.items():
            if physical_drive in self._semaphores:
                # Get current semaphore
                semaphore = self._semaphores[physical_drive]
                current_limit = semaphore._value
                
                if current_limit != limit:
                    # Update semaphore with new limit
                    # Note: We can't directly modify the semaphore's value,
                    # so we create a new one with the updated limit
                    new_semaphore = asyncio.Semaphore(limit)
                    self._semaphores[physical_drive] = new_semaphore
                    logger.info(f"Updated semaphore for physical drive {physical_drive}: {current_limit} → {limit}")
            else:
                # Create new semaphore
                self._semaphores[physical_drive] = asyncio.Semaphore(limit)
                logger.info(f"Created new semaphore for physical drive {physical_drive} with limit {limit}")


# Create a singleton instance
disk_io_service = DiskIOService()
