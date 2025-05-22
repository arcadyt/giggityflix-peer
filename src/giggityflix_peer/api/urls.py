# src/giggityflix_peer/api/urls.py (update)
from django.urls import path, include
from giggityflix_peer.apps.drive_detection.drive_views import PhysicalDriveViewSet, PartitionViewSet
from giggityflix_peer.views.configuration_views import ConfigurationViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'drives', PhysicalDriveViewSet)
router.register(r'partitions', PartitionViewSet)
router.register(r'configurations', ConfigurationViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
