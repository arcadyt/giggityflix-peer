import asyncio
import logging
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class DriveDetectionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'giggityflix_mgmt_peer.apps.drive_detection'
    label = 'drive_detection'

    def ready(self):
        """Initialize drive detection on startup."""
        # Skip initialization during migrations or when collecting static files
        if any(cmd in sys.argv for cmd in ['makemigrations', 'migrate', 'collectstatic', 'test']):
            return

        # Import here to avoid app registry not ready error
        try:
            from giggityflix_mgmt_peer.apps.drive_detection import get_drive_service

            # Get the service instance
            drive_service = get_drive_service()
            
            # Execute drive detection in a background thread with proper error handling
            import threading
            
            def detect_drives_thread():
                try:
                    result = drive_service.detect_and_persist_drives()
                    logger.info(f"Drive detection completed: {result}")
                except Exception as e:
                    logger.error(f"Drive detection failed: {str(e)}", exc_info=True)
            
            thread = threading.Thread(target=detect_drives_thread)
            thread.daemon = True
            thread.start()
            logger.info("Drive detection started in background thread")
            
        except Exception as e:
            logger.error(f"Failed to initialize drive detection: {str(e)}", exc_info=True)
