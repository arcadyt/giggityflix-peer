from django.apps import AppConfig


class MediaConfig(AppConfig):
    name = 'giggityflix_peer.apps.media'
    label = 'media'
    verbose_name = 'GiggityFlix Media'

    def ready(self):
        """Initialize app on startup."""
        # Import signal handlers to register them
        from . import receivers  # noqa
