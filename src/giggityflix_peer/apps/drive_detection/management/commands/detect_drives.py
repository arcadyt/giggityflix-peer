"""Command to detect and persist drives."""
import logging
from django.core.management.base import BaseCommand

from giggityflix_mgmt_peer.apps.drive_detection import get_drive_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Detect and persist drives to the database'

    def handle(self, *args, **options):
        try:
            service = get_drive_service()
            result = service.detect_and_persist_drives()
            self.stdout.write(self.style.SUCCESS(f"Drive detection completed: {result}"))
        except Exception as e:
            logger.error(f"Drive detection failed: {e}", exc_info=True)
            self.stdout.write(self.style.ERROR(f"Drive detection failed: {e}"))
