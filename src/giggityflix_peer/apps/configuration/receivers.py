import logging
from django.dispatch import receiver
from .signals import configuration_changed

logger = logging.getLogger(__name__)


# Cache invalidation handler
@receiver(configuration_changed)
def invalidate_config_cache(sender, key, value, **kwargs):
    """Clear configuration cache when a configuration changes."""
    from . import services

    # Clear specific key from cache
    if key in services._CACHE:
        del services._CACHE[key]

    logger.debug(f"Configuration changed: {key} = {value}")


# You can add other receivers for specific keys
# Example: Listen for specific configuration changes
@receiver(configuration_changed)
def handle_log_level_change(sender, key, value, **kwargs):
    """Update logging configuration when log_level changes."""
    if key == "log_level" and value:
        import logging
        logging.getLogger("giggityflix_mgmt_peer").setLevel(value)
        logger.info(f"Set log level to {value}")


# Example: React to auto_discovery setting
@receiver(configuration_changed)
def handle_auto_discovery_change(sender, key, value, **kwargs):
    """Handle changes to auto_discovery setting."""
    if key == "enable_auto_discovery":
        if value:
            logger.info("Auto-discovery enabled, will run on next startup")
        else:
            logger.info("Auto-discovery disabled")