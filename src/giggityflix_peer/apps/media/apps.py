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
        
        # Ensure configuration app is ready first
        try:
            from giggityflix_peer.apps.configuration import services as config_service
            # Test configuration access to ensure it's ready
            config_service.get('media_dirs', [])
            logger.info("Media app initialized - configuration service ready")
        except Exception as e:
            logger.warning(f"Media app initialized but configuration service not ready: {e}")
