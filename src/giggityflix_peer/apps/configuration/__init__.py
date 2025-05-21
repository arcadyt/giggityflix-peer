"""
Configuration application for the Giggityflix Management Peer service.

This package provides configuration management functionality.
"""

default_app_config = 'giggityflix_mgmt_peer.apps.configuration.apps.ConfigurationConfig'

# DO NOT import models, services, or other Django components directly at module level

# This is needed to support existing code - don't use it in new code
class LazyConfiguration:
    def __getattr__(self, name):
        from .models import Configuration as RealConfiguration
        return getattr(RealConfiguration, name)

# Create a lazy proxy that loads the real Configuration only when accessed
Configuration = LazyConfiguration()
