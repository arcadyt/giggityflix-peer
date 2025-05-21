import logging
import os
from typing import Any, Dict, Optional, List

from django.db import transaction

from .models import Configuration

logger = logging.getLogger(__name__)

# Simple cache to avoid repeated database lookups
_CACHE = {}

def get(key: str, default: Any = None) -> Any:
    """
    Get a configuration value by key.
    
    Args:
        key: The configuration key
        default: Default value if configuration doesn't exist
        
    Returns:
        The typed configuration value
    """
    # Check cache first
    if key in _CACHE:
        return _CACHE[key]
    
    # Try to get from database
    try:
        config = Configuration.objects.get(key=key)
        value = config.get_typed_value()
        _CACHE[key] = value
        return value
    except Configuration.DoesNotExist:
        return default

def set(key: str, value: Any, value_type: Optional[str] = None, 
        description: Optional[str] = None, 
        is_env_overridable: Optional[bool] = None,
        env_variable: Optional[str] = None, 
        default_value: Optional[Any] = None) -> bool:
    """
    Set a configuration value.
    
    Args:
        key: The configuration key
        value: The value to set
        value_type: The value type (optional, only used for new configurations)
        description: Description (optional)
        is_env_overridable: Whether the value can be overridden by env vars
        env_variable: Environment variable name for override
        default_value: Default value
        
    Returns:
        True if successful, False otherwise
    """
    # Clear cache for this key
    if key in _CACHE:
        del _CACHE[key]
    
    try:
        with transaction.atomic():
            # Get or create the configuration
            config, created = Configuration.objects.get_or_create(key=key)
            
            # Set fields if provided
            if created and value_type:
                config.value_type = value_type
            if description is not None:
                config.description = description
            if is_env_overridable is not None:
                config.is_env_overridable = is_env_overridable
            if env_variable is not None:
                config.env_variable = env_variable
            if default_value is not None:
                config.default_value = config._to_storage_format(default_value)
            
            # Set the value and save
            config.set_typed_value(value)
            config.save()
            
        return True
    except Exception as e:
        logger.error(f"Error setting configuration '{key}': {e}")
        return False

def delete(key: str) -> bool:
    """
    Delete a configuration property.
    
    Args:
        key: The configuration key
        
    Returns:
        True if successful, False otherwise
    """
    # Clear cache for this key
    if key in _CACHE:
        del _CACHE[key]
    
    try:
        count, _ = Configuration.objects.filter(key=key).delete()
        return count > 0
    except Exception as e:
        logger.error(f"Error deleting configuration '{key}': {e}")
        return False

def get_all() -> Dict[str, Any]:
    """
    Get all configuration values.
    
    Returns:
        Dictionary of configuration keys and their typed values
    """
    result = {}
    configs = Configuration.objects.all()
    
    for config in configs:
        key = config.key
        value = config.get_typed_value()
        result[key] = value
        _CACHE[key] = value
    
    return result

def load_from_environment() -> List[str]:
    """
    Load configuration values from environment variables.
    
    Returns:
        List of keys that were updated from environment variables
    """
    updated_keys = []
    
    # Get all configurations that can be overridden
    configs = Configuration.objects.filter(is_env_overridable=True).exclude(env_variable='').exclude(env_variable=None)
    
    for config in configs:
        if config.env_variable in os.environ:
            env_value = os.environ[config.env_variable]
            
            # Update the configuration
            old_value = config.set_typed_value(env_value)
            if old_value != config.get_typed_value():  # Only save if value changed
                config.save()
                updated_keys.append(config.key)
                
                # Clear cache
                if config.key in _CACHE:
                    del _CACHE[key]
                
                logger.info(f"Configuration '{config.key}' updated from environment variable '{config.env_variable}'")
    
    return updated_keys

def ensure_defaults() -> List[str]:
    """
    Ensure default configurations exist.
    
    Returns:
        List of keys that were created
    """
    created_keys = []
    defaults = [
        {
            'key': 'scraping_paths',
            'default_value': '',
            'value_type': Configuration.TYPE_LIST,
            'description': 'List of paths to scan for media files',
            'is_env_overridable': True,
            'env_variable': 'GIGGITYFLIX_SCRAPING_PATHS'
        },
        {
            'key': 'api_port',
            'default_value': '8000',
            'value_type': Configuration.TYPE_INTEGER,
            'description': 'Port for the management REST API',
            'is_env_overridable': True,
            'env_variable': 'GIGGITYFLIX_API_PORT'
        },
        {
            'key': 'log_level',
            'default_value': 'INFO',
            'value_type': Configuration.TYPE_STRING,
            'description': 'Logging level for the application',
            'is_env_overridable': True,
            'env_variable': 'GIGGITYFLIX_LOG_LEVEL'
        },
        {
            'key': 'db_path',
            'default_value': 'db.sqlite3',
            'value_type': Configuration.TYPE_STRING,
            'description': 'Path to SQLite database file',
            'is_env_overridable': True,
            'env_variable': 'GIGGITYFLIX_DB_PATH'
        },
        {
            'key': 'scan_interval_minutes',
            'default_value': '60',
            'value_type': Configuration.TYPE_INTEGER,
            'description': 'Interval in minutes between media scans',
            'is_env_overridable': True,
            'env_variable': 'GIGGITYFLIX_SCAN_INTERVAL'
        },
        {
            'key': 'enable_auto_discovery',
            'default_value': 'true',
            'value_type': Configuration.TYPE_BOOLEAN,
            'description': 'Automatically discover drives on startup',
            'is_env_overridable': True,
            'env_variable': 'GIGGITYFLIX_AUTO_DISCOVERY'
        }
    ]

    for config_data in defaults:
        try:
            # Check if config exists
            if not Configuration.objects.filter(key=config_data['key']).exists():
                # Create new config with defaults
                config = Configuration(
                    key=config_data['key'],
                    default_value=config_data['default_value'],
                    value_type=config_data['value_type'],
                    description=config_data['description'],
                    is_env_overridable=config_data['is_env_overridable'],
                    env_variable=config_data['env_variable']
                )
                config.save()
                created_keys.append(config.key)
                logger.info(f"Created default configuration '{config.key}'")
        except Exception as e:
            logger.error(f"Error creating default configuration '{config_data['key']}': {e}")
    
    return created_keys

def initialize():
    """Initialize the configuration service."""
    # Create default configurations
    ensure_defaults()
    
    # Load from environment variables
    load_from_environment()
    
    # Clear cache to ensure fresh values
    _CACHE.clear()
    
    logger.info("Configuration service initialized")
