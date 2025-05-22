from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/config/', include('giggityflix_peer.apps.configuration.urls')),
    path('api/drives/', include('giggityflix_peer.apps.drive_detection.interfaces.urls')),
    path('api/media/', include('giggityflix_peer.apps.media.interfaces.urls')),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
