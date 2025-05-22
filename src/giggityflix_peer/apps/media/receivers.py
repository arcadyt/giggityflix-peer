"""Signal receivers for media app."""
import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .infrastructure.models import MediaFile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=MediaFile)
def handle_media_file_saved(sender, instance, created, **kwargs):
    """Handle media file saved signal."""
    if created:
        logger.info(f"New media file added: {instance.luid}")
    else:
        logger.debug(f"Media file updated: {instance.luid}")


@receiver(post_delete, sender=MediaFile)
def handle_media_file_deleted(sender, instance, **kwargs):
    """Handle media file deleted signal."""
    logger.info(f"Media file deleted: {instance.luid}")
