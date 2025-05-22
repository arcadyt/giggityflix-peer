import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MediaConfig(AppConfig):
    name = 'giggityflix_peer.apps.media'
    label = 'media'
    verbose_name = 'GiggityFlix Media'

    def ready(self):
        """Initialize app on startup."""
        # Skip during migrations or management commands that don't need initialization
        if any(cmd in sys.argv for cmd in ['makemigrations', 'migrate', 'collectstatic', 'test']):
            return

        # Import signal handlers to register them
        from . import receivers  # noqa
        
        logger.info("Media app initialized")
