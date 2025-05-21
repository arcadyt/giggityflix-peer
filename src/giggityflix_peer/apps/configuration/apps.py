from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ConfigurationConfig(AppConfig):
    name = 'giggityflix_mgmt_peer.apps.configuration'
    label = 'configuration'

    def ready(self):
        """Initialize configuration service when app is ready."""
        # Import services module
        from . import services

        # Avoid circular imports
        from . import receivers

        # Initialize after migrations
        post_migrate.connect(self._post_migrate_handler, sender=self)

    def _post_migrate_handler(self, sender, **kwargs):
        """Initialize configuration after migrations."""
        from . import services
        services.initialize()