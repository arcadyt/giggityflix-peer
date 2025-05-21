from django.urls import path, include
from rest_framework.routers import DefaultRouter

from giggityflix_mgmt_peer.apps.drive_detection.views import PhysicalDriveViewSet, PartitionViewSet

# Create a router for drive detection endpoints
router = DefaultRouter()
router.register('drives', PhysicalDriveViewSet, basename='drive')
router.register('partitions', PartitionViewSet, basename='partition')

urlpatterns = [
    path('', include(router.urls)),
]
