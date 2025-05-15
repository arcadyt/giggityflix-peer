import json
import logging
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
