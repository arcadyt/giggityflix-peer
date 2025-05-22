import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MediaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'giggityflix_peer.apps.media'
    label = 'media'
    verbose_name = 'GiggityFlix Media'

    def ready(self):
        """Initialize app after configuration is ready."""
        # Skip during migrations or management commands that don't need initialization
        if any(cmd in sys.argv for cmd in ['makemigrations', 'migrate', 'collectstatic', 'test']):
            return

        # Import signal handlers to register them
        from . import receivers  # noqa
        
        # Verify configuration app is ready
        try:
            from giggityflix_peer.apps.configuration import services as config_service
            # Test configuration access to ensure it's ready
            # Don't actually call async functions here, just verify import works
            logger.info("Media app ready - configuration service available")
        except Exception as e:
            logger.warning(f"Media app ready but configuration service not available: {e}")

        # Log that media app is properly configured for DI
        logger.info("Media app initialized - services available for dependency injection")
