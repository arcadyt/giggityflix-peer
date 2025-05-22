"""Signal receivers for media app."""
import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .infrastructure.models import MediaFile
from .application.grpc_service import get_media_grpc_service
from .infrastructure.repositories import get_media_repository

logger = logging.getLogger(__name__)


@receiver(post_save, sender=MediaFile)
def handle_media_file_saved(sender, instance, created, **kwargs):
    """Handle media file saved signal."""
    if created:
        logger.info(f"New media file added: {instance.luid}")
        
        # Convert ORM to domain model and announce if ready
        try:
            media_repo = get_media_repository()
            media = media_repo.get_by_luid(instance.luid)
            
            if media and media.status.value == 'ready':
                grpc_service = get_media_grpc_service()
                if grpc_service.is_connected():
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        loop.create_task(grpc_service.update_catalog_status(media))
                    except RuntimeError:
                        # No event loop running, skip gRPC announcement
                        pass
        except Exception as e:
            logger.error(f"Error handling media file save: {e}")
    else:
        logger.debug(f"Media file updated: {instance.luid}")


@receiver(post_delete, sender=MediaFile)
def handle_media_file_deleted(sender, instance, **kwargs):
    """Handle media file deleted signal."""
    logger.info(f"Media file deleted: {instance.luid}")
