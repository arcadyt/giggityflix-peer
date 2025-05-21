"""URL configuration for media app."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

# Create a router for media endpoints
router = DefaultRouter()
router.register(r'files', views.MediaFileViewSet, basename='media')
router.register(r'screenshots', views.ScreenshotViewSet, basename='screenshot')

urlpatterns = [
    path('', include(router.urls)),
]
