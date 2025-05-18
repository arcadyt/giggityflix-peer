import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from giggityflix_peer.db.sqlite import db

logger = logging.getLogger(__name__)


class ConfigService:
    """Service for managing application configuration."""

    def __init__(self):
        """Initialize the configuration service."""
        self._cache = {}
        self._defaults = {
            # Original settings (preserved)
            "data_dir": (str(Path.home() / ".giggityflix"), "str", "Base directory for all peer data", False),
            "media_dirs": ("[]", "json", "Directories to scan for media", True),
            "exclude_dirs": ("[]", "json", "Directories to exclude from scanning", True),
            "include_extensions": ('[".mp4",".mkv",".avi",".mov"]', "json", "File extensions to include", True),
            "scan_interval_minutes": ("60", "int", "Interval between automatic scans", True),
            "http_port": ("8080", "int", "Port for the HTTP server", True),
            "extract_metadata": ("true", "bool", "Extract metadata from media files", True),
            "screenshot_cache_size_mb": ("100", "int", "Size of screenshot cache in MB", True),

            # gRPC connection settings (preserved)
            "edge_address": ("localhost:50051", "str", "Address of the Edge Service", True),
            "use_tls": ("false", "bool", "Use TLS for gRPC connection", True),
            "cert_path": ("", "str", "Path to TLS certificate file", True),
            "grpc_timeout_sec": ("30", "int", "Timeout for gRPC requests in seconds", True),
            "heartbeat_interval_sec": ("30", "int", "Interval for sending heartbeats in seconds", True),
            "max_reconnect_attempts": ("5", "int", "Maximum number of reconnection attempts", True),
            "reconnect_interval_sec": ("10", "int", "Initial interval between reconnection attempts in seconds", True),

            # Resource management settings (added)
            "process_pool_size": (
                str(os.cpu_count() or 4), "int", "Number of process pool workers for CPU-bound tasks", True),
            "default_io_limit": ("2", "int", "Default concurrent IO operations per storage resource", True),
            "storage_resources": ("[]", "json", "Detected storage resources and their IO limits", True),
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

            # Load all settings into cache
            await self._reload_cache()

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

        # If updating media_dirs, update storage resources
        if key == "media_dirs":
            await self._update_storage_resources()

        return True

    async def _update_storage_resources(self):
        """Update storage resources based on media directories."""
        media_dirs = await self.get("media_dirs", [])
        default_io_limit = await self.get("default_io_limit", 2)

        # Get existing storage resources
        existing_resources = await self.get("storage_resources", [])
        existing_dict = {res["path"]: res for res in existing_resources}

        # Detect storage resources for each media directory
        resources = []
        storage_paths = set()

        for directory in media_dirs:
            path = Path(directory)
            if not path.exists():
                continue

            storage_path = self._get_storage_path(path)
            if storage_path in storage_paths:
                continue

            storage_paths.add(storage_path)

            # Create or update resource
            if storage_path in existing_dict:
                resources.append(existing_dict[storage_path])
            else:
                resources.append({
                    "path": storage_path,
                    "io_limit": default_io_limit,
                    "description": self._get_storage_description(storage_path)
                })

        # Save updated resources
        await self.set("storage_resources", resources)

    def _get_storage_path(self, path: Path) -> str:
        """Get the storage path for a directory."""
        # On Windows, return the drive letter
        if os.name == 'nt':
            return path.drive

        # On Unix, try to get the mount point
        # This is a simplified version - a more robust version would use os.stat
        # and match against mounted filesystems
        path_str = str(path.absolute())
        return '/'  # Default to root as a fallback

    def _get_storage_description(self, storage_path: str) -> str:
        """Get a user-friendly description for a storage path."""
        if os.name == 'nt':
            # On Windows, try to get volume information
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                volume_name_buffer = ctypes.create_unicode_buffer(1024)
                filesystem_name_buffer = ctypes.create_unicode_buffer(1024)
                if kernel32.GetVolumeInformationW(storage_path + "\\", volume_name_buffer,
                                                  1024, None, None, None,
                                                  filesystem_name_buffer, 1024):
                    volume_name = volume_name_buffer.value
                    if volume_name:
                        return f"{storage_path} ({volume_name})"
            except:
                pass

        return storage_path

    async def get_storage_resource(self, path: str) -> Dict[str, Any]:
        """Get storage resource configuration for a path."""
        storage_path = self._get_storage_path(Path(path))

        resources = await self.get("storage_resources", [])
        for resource in resources:
            if resource["path"] == storage_path:
                return resource

        # If not found, return default
        default_io_limit = await self.get("default_io_limit", 2)
        return {
            "path": storage_path,
            "io_limit": default_io_limit,
            "description": self._get_storage_description(storage_path)
        }

    async def update_storage_resource(self, path: str, io_limit: int) -> bool:
        """Update IO limit for a storage resource."""
        if io_limit <= 0:
            return False

        resources = await self.get("storage_resources", [])
        updated = False

        for resource in resources:
            if resource["path"] == path:
                resource["io_limit"] = io_limit
                updated = True
                break

        if not updated:
            # Add as a new resource
            resources.append({
                "path": path,
                "io_limit": io_limit,
                "description": self._get_storage_description(path)
            })

        # Save updated resources
        await self.set("storage_resources", resources)
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


# Create a singleton service instance
config_service = ConfigService()
