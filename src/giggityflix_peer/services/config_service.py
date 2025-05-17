import json
import logging
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from giggityflix_peer.db.sqlite import db

logger = logging.getLogger(__name__)


def get_drive_info_for_path(path: str) -> Tuple[str, str]:
    """Get drive ID and physical drive ID for a path.
    
    Returns:
        A tuple of (drive_id, physical_drive)
    """
    path_obj = Path(path)
    system = platform.system()
    
    # Windows: use drive letter
    if system == "Windows":
        if path_obj.drive:
            drive_id = path_obj.drive.upper()
            return drive_id, drive_id
        return str(path_obj), str(path_obj)
    
    # Linux/macOS: use mount point and device
    try:
        result = subprocess.run(
            ["df", "-P", str(path_obj)],
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            parts = lines[1].split()
            device = parts[0]  # Device
            
            # Drive ID is the mount point
            drive_id = parts[5] if len(parts) > 5 else str(path_obj)
            
            # Get physical drive (strip partition number for conventional devices)
            if device.startswith('/dev/'):
                if 'nvme' in device:
                    # NVMe devices: /dev/nvme0n1p1 -> /dev/nvme0n1
                    nvme_parts = device.split('p')
                    if len(nvme_parts) > 1 and nvme_parts[-1].isdigit():
                        return drive_id, nvme_parts[0]
                else:
                    # Standard devices: /dev/sda1 -> /dev/sda
                    if device[-1].isdigit():
                        base_device = device.rstrip('0123456789')
                        if base_device:
                            return drive_id, base_device
            
            return drive_id, device
    except Exception as e:
        logger.error(f"Error getting drive info for path {path}: {e}")
    
    return str(path_obj), str(path_obj)


class ConfigService:
    """Service for managing application configuration."""

    def __init__(self):
        """Initialize the configuration service."""
        self._cache = {}
        self._defaults = {
            # System settings (non-editable through API)
            "data_dir": (str(Path.home() / ".giggityflix"), "str", "Base directory for all peer data", False),
            
            # User-configurable settings
            "media_dirs": ("[]", "json", "Directories to scan for media", True),
            "exclude_dirs": ("[]", "json", "Directories to exclude from scanning", True),
            "include_extensions": ('[".mp4",".mkv",".avi",".mov"]', "json", "File extensions to include", True),
            "scan_interval_minutes": ("60", "int", "Interval between automatic scans", True),
            "http_port": ("8080", "int", "Port for the HTTP server", True),
            "extract_metadata": ("true", "bool", "Extract metadata from media files", True),
            "screenshot_cache_size_mb": ("100", "int", "Size of screenshot cache in MB", True),
            
            # gRPC connection settings
            "edge_address": ("localhost:50051", "str", "Address of the Edge Service", True),
            "use_tls": ("false", "bool", "Use TLS for gRPC connection", True),
            "cert_path": ("", "str", "Path to TLS certificate file", True),
            "grpc_timeout_sec": ("30", "int", "Timeout for gRPC requests in seconds", True),
            "heartbeat_interval_sec": ("30", "int", "Interval for sending heartbeats in seconds", True),
            "max_reconnect_attempts": ("5", "int", "Maximum number of reconnection attempts", True),
            "reconnect_interval_sec": ("10", "int", "Initial interval between reconnection attempts in seconds", True),
        }
    
    async def initialize(self):
        """Initialize configuration with defaults if not present."""
        async with db.transaction():
            for key, (default_value, value_type, description, editable) in self._defaults.items():
                # Check if setting exists
                setting = await db.execute_and_fetchone(
                    "SELECT * FROM settings WHERE key = ?", (key,)
                )
                
                if not setting:
                    # Insert default value
                    await db.execute(
                        """
                        INSERT INTO settings (key, value, value_type, description, editable, last_updated) 
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (key, default_value, value_type, description, editable, datetime.now().isoformat())
                    )
            
            # Initialize drive_configs table
            await self.initialize_drive_configs()
            
            # Load all settings into cache
            await self._reload_cache()
            
            # Update drive configurations based on media directories
            await self.update_drive_configs_from_media_dirs()
    
    async def initialize_drive_configs(self):
        """Initialize drive configurations table."""
        async with db.transaction():
            # Create drive_configs table if it doesn't exist
            await db.execute("""
            CREATE TABLE IF NOT EXISTS drive_configs (
                drive_id TEXT PRIMARY KEY,
                physical_drive TEXT NOT NULL,
                concurrent_operations INT NOT NULL DEFAULT 1,
                last_updated TEXT NOT NULL
            )
            """)
    
    async def _reload_cache(self):
        """Reload all settings into memory cache."""
        settings = await db.execute_and_fetchall("SELECT * FROM settings")
        self._cache = {}
        
        for setting in settings:
            self._cache[setting['key']] = self._convert_value(setting['value'], setting['value_type'])
    
    def _convert_value(self, value: str, value_type: str) -> Any:
        """Convert value from string to the appropriate type."""
        if value_type == "int":
            return int(value)
        elif value_type == "bool":
            return value.lower() == "true"
        elif value_type == "json":
            return json.loads(value)
        # Default to string
        return value
    
    def _convert_to_string(self, value: Any, value_type: str) -> str:
        """Convert value to string based on type."""
        if value_type == "json":
            return json.dumps(value)
        elif value_type == "bool":
            return str(value).lower()
        return str(value)
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        if key in self._cache:
            return self._cache[key]
        return default
    
    async def set(self, key: str, value: Any) -> bool:
        """Set a configuration value."""
        setting = await db.execute_and_fetchone(
            "SELECT * FROM settings WHERE key = ?", (key,)
        )
        
        if not setting:
            raise ValueError(f"Setting {key} does not exist")
        
        if not setting['editable']:
            raise ValueError(f"Setting {key} is not editable")
        
        # Convert value to string based on type
        value_type = setting['value_type']
        str_value = self._convert_to_string(value, value_type)
        
        # Update in database
        await db.execute(
            "UPDATE settings SET value = ?, last_updated = ? WHERE key = ?",
            (str_value, datetime.now().isoformat(), key)
        )
        
        # Update cache
        self._cache[key] = value
        
        # If media_dirs changed, update drive configurations
        if key == "media_dirs":
            await self.update_drive_configs_from_media_dirs()
        
        return True
    
    async def get_all(self, editable_only: bool = False) -> Dict[str, Dict[str, Union[str, Any]]]:
        """Get all settings."""
        query = "SELECT * FROM settings"
        if editable_only:
            query += " WHERE editable = TRUE"
        
        settings = await db.execute_and_fetchall(query)
        
        result = {}
        for setting in settings:
            result[setting['key']] = {
                "value": self._convert_value(setting['value'], setting['value_type']),
                "value_type": setting['value_type'],
                "description": setting['description'],
                "editable": setting['editable'],
                "last_updated": setting['last_updated']
            }
        
        return result
    
    async def get_setting(self, key: str) -> Optional[Dict[str, Union[str, Any]]]:
        """Get details about a specific setting."""
        setting = await db.execute_and_fetchone(
            "SELECT * FROM settings WHERE key = ?", (key,)
        )
        
        if not setting:
            return None
        
        return {
            "key": setting['key'],
            "value": self._convert_value(setting['value'], setting['value_type']),
            "value_type": setting['value_type'],
            "description": setting['description'],
            "editable": setting['editable'],
            "last_updated": setting['last_updated']
        }
    
    async def get_drive_config(self, drive_id: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific drive."""
        result = await db.execute_and_fetchone(
            "SELECT * FROM drive_configs WHERE drive_id = ?", (drive_id,)
        )
        
        if not result:
            return None
        
        return {
            "drive_id": result["drive_id"],
            "physical_drive": result["physical_drive"],
            "concurrent_operations": result["concurrent_operations"],
            "last_updated": result["last_updated"]
        }
    
    async def get_all_drive_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get configurations for all drives."""
        results = await db.execute_and_fetchall("SELECT * FROM drive_configs")
        
        configs = {}
        for result in results:
            configs[result["drive_id"]] = {
                "drive_id": result["drive_id"],
                "physical_drive": result["physical_drive"],
                "concurrent_operations": result["concurrent_operations"],
                "last_updated": result["last_updated"]
            }
        
        return configs
    
    async def set_drive_config(self, drive_id: str, concurrent_operations: int) -> bool:
        """Set or update configuration for a specific drive."""
        # Get current drive configuration if it exists
        existing = await self.get_drive_config(drive_id)
        
        # Get physical drive information if needed
        physical_drive = None
        if existing:
            physical_drive = existing["physical_drive"]
        else:
            # Try to get physical drive ID
            media_dirs = await self.get("media_dirs", [])
            
            # Find a media dir on this drive
            for directory in media_dirs:
                dir_drive_id, dir_physical_drive = get_drive_info_for_path(directory)
                if dir_drive_id == drive_id:
                    physical_drive = dir_physical_drive
                    break
            
            # If still no physical drive, use drive_id as fallback
            if not physical_drive:
                physical_drive = drive_id
        
        # Update or insert drive configuration
        async with db.transaction():
            if existing:
                # Update existing configuration
                await db.execute(
                    """
                    UPDATE drive_configs 
                    SET concurrent_operations = ?, last_updated = ? 
                    WHERE drive_id = ?
                    """,
                    (concurrent_operations, datetime.now().isoformat(), drive_id)
                )
            else:
                # Insert new configuration
                await db.execute(
                    """
                    INSERT INTO drive_configs 
                    (drive_id, physical_drive, concurrent_operations, last_updated) 
                    VALUES (?, ?, ?, ?)
                    """,
                    (drive_id, physical_drive, concurrent_operations, datetime.now().isoformat())
                )
        
        return True
    
    async def get_physical_drives(self) -> Dict[str, List[str]]:
        """Get mapping of physical drives to their logical drives."""
        results = await db.execute_and_fetchall("SELECT drive_id, physical_drive FROM drive_configs")
        
        drives = {}
        for result in results:
            physical = result["physical_drive"]
            drive_id = result["drive_id"]
            
            if physical not in drives:
                drives[physical] = []
            
            drives[physical].append(drive_id)
        
        return drives
    
    async def get_max_concurrent_operations(self, drive_id: str) -> int:
        """Get maximum concurrent operations for a drive."""
        config = await self.get_drive_config(drive_id)
        if config:
            return config["concurrent_operations"]
        return 1  # Default is 1
    
    async def update_drive_configs_from_media_dirs(self) -> None:
        """Update drive configurations based on configured media directories."""
        media_dirs = await self.get("media_dirs", [])
        drive_ids_set = set()
        
        for directory in media_dirs:
            drive_id, physical_drive = get_drive_info_for_path(directory)
            if drive_id:
                drive_ids_set.add(drive_id)
                
                # Check if drive config exists
                config = await self.get_drive_config(drive_id)
                if not config:
                    # Add default config for this drive
                    await db.execute(
                        """
                        INSERT INTO drive_configs 
                        (drive_id, physical_drive, concurrent_operations, last_updated) 
                        VALUES (?, ?, ?, ?)
                        """,
                        (drive_id, physical_drive, 1, datetime.now().isoformat())
                    )
        
        # We don't remove old drive configs because they might be temporarily unused
        # but still valid for future configuration.
    
    async def get_drive_for_path(self, path: str) -> Dict[str, Any]:
        """Get drive configuration for a specific path."""
        drive_id, physical_drive = get_drive_info_for_path(path)
        config = await self.get_drive_config(drive_id)
        
        if not config:
            # Create and return default configuration
            return {
                "drive_id": drive_id,
                "physical_drive": physical_drive,
                "concurrent_operations": 1
            }
        
        return config


# Create a singleton service instance
config_service = ConfigService()
