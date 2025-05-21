from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('giggityflix_mgmt_peer.config.urls')),
    path('api/', include('giggityflix_mgmt_peer.apps.drive_detection.interfaces.urls')),
]
