from django.urls import path, include
from rest_framework.routers import DefaultRouter

from giggityflix_mgmt_peer.apps.configuration.views import ConfigurationViewSet

# Create a router for configuration endpoints
router = DefaultRouter()
router.register('configurations', ConfigurationViewSet, basename='configuration')

urlpatterns = [
    path('', include(router.urls)),
]
