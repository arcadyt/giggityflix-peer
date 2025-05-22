from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ConfigurationViewSet

# Create a router for configuration endpoints
router = DefaultRouter()
router.register('', ConfigurationViewSet, basename='configuration')

urlpatterns = [
    path('', include(router.urls)),
]
