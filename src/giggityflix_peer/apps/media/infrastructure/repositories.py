"""Repositories for media domain objects."""
from datetime import datetime
from typing import Dict, List, Optional

from django.db import transaction

from ..domain.models import Media, MediaStatus, MediaType, Screenshot
from .models import MediaFile as OrmMediaFile
from .models import MediaHash as OrmMediaHash
from .models import Screenshot as OrmScreenshot


class MediaRepository:
    """Repository for Media domain objects."""
    
    def get_by_luid(self, luid: str) -> Optional[Media]:
        """Get a media file by its local unique ID."""
        try:
            orm_media = OrmMediaFile.objects.get(luid=luid)
            return self._orm_to_domain(orm_media)
        except OrmMediaFile.DoesNotExist:
            return None
    
    def get_by_path(self, path: str) -> Optional[Media]:
        """Get a media file by its path."""
        try:
            orm_media = OrmMediaFile.objects.get(path=path)
            return self._orm_to_domain(orm_media)
        except OrmMediaFile.DoesNotExist:
            return None
            
    def get_by_catalog_id(self, catalog_id: str) -> Optional[Media]:
        """Get a media file by its catalog ID."""
        try:
            orm_media = OrmMediaFile.objects.get(catalog_id=catalog_id)
            return self._orm_to_domain(orm_media)
        except OrmMediaFile.DoesNotExist:
            return None
    
    def get_all(self) -> List[Media]:
        """Get all media files."""
        orm_media_files = OrmMediaFile.objects.all().prefetch_related('hashes')
        return [self._orm_to_domain(orm_media) for orm_media in orm_media_files]
    
    def get_by_status(self, status: MediaStatus) -> List[Media]:
        """Get media files by status."""
        orm_media_files = OrmMediaFile.objects.filter(
            status=status.value
        ).prefetch_related('hashes')
        return [self._orm_to_domain(orm_media) for orm_media in orm_media_files]
    
    @transaction.atomic
    def save(self, media: Media) -> None:
        """Save a media file."""
        # Check if media exists
        try:
            orm_media = OrmMediaFile.objects.get(luid=media.luid)
            # Update existing
            orm_media.catalog_id = media.catalog_id
            orm_media.path = media.path
            orm_media.relative_path = media.relative_path
            orm_media.size_bytes = media.size_bytes
            orm_media.media_type = media.media_type.value
            orm_media.status = media.status.value
            orm_media.modified_at = media.modified_at
            orm_media.last_accessed = media.last_accessed
            orm_media.duration_seconds = media.duration_seconds
            orm_media.width = media.width
            orm_media.height = media.height
            orm_media.codec = media.codec
            orm_media.bitrate = media.bitrate
            orm_media.framerate = media.framerate
            orm_media.view_count = media.view_count
            orm_media.last_viewed = media.last_viewed
            orm_media.error_message = media.error_message
            orm_media.save()
            
            # Update hashes - delete existing ones and add new ones
            orm_media.hashes.all().delete()
            
        except OrmMediaFile.DoesNotExist:
            # Create new
            orm_media = OrmMediaFile.objects.create(
                luid=media.luid,
                catalog_id=media.catalog_id,
                path=media.path,
                relative_path=media.relative_path,
                size_bytes=media.size_bytes,
                media_type=media.media_type.value,
                status=media.status.value,
                modified_at=media.modified_at,
                last_accessed=media.last_accessed,
                duration_seconds=media.duration_seconds,
                width=media.width,
                height=media.height,
                codec=media.codec,
                bitrate=media.bitrate,
                framerate=media.framerate,
                view_count=media.view_count,
                last_viewed=media.last_viewed,
                error_message=media.error_message
            )
        
        # Add hashes
        for algorithm, hash_value in media.hashes.items():
            OrmMediaHash.objects.create(
                media=orm_media,
                algorithm=algorithm,
                hash_value=hash_value
            )
    
    @transaction.atomic
    def delete(self, luid: str) -> bool:
        """Delete a media file."""
        try:
            OrmMediaFile.objects.get(luid=luid).delete()
            return True
        except OrmMediaFile.DoesNotExist:
            return False
    
    def _orm_to_domain(self, orm_media: OrmMediaFile) -> Media:
        """Convert ORM model to domain model."""
        # Build hashes dictionary
        hashes = {h.algorithm: h.hash_value for h in orm_media.hashes.all()}
        
        return Media(
            luid=orm_media.luid,
            catalog_id=orm_media.catalog_id,
            path=orm_media.path,
            relative_path=orm_media.relative_path,
            size_bytes=orm_media.size_bytes,
            media_type=MediaType(orm_media.media_type),
            status=MediaStatus(orm_media.status),
            created_at=orm_media.created_at,
            modified_at=orm_media.modified_at,
            last_accessed=orm_media.last_accessed,
            duration_seconds=orm_media.duration_seconds,
            width=orm_media.width,
            height=orm_media.height,
            codec=orm_media.codec,
            bitrate=orm_media.bitrate,
            framerate=orm_media.framerate,
            hashes=hashes,
            view_count=orm_media.view_count,
            last_viewed=orm_media.last_viewed,
            error_message=orm_media.error_message
        )


class ScreenshotRepository:
    """Repository for Screenshot domain objects."""
    
    def get_by_id(self, id: str) -> Optional[Screenshot]:
        """Get a screenshot by ID."""
        try:
            orm_screenshot = OrmScreenshot.objects.get(id=id)
            return self._orm_to_domain(orm_screenshot)
        except OrmScreenshot.DoesNotExist:
            return None
    
    def get_for_media(self, media_luid: str) -> List[Screenshot]:
        """Get all screenshots for a media file."""
        orm_screenshots = OrmScreenshot.objects.filter(media_id=media_luid)
        return [self._orm_to_domain(s) for s in orm_screenshots]
    
    @transaction.atomic
    def save(self, screenshot: Screenshot) -> None:
        """Save a screenshot."""
        try:
            # Try to update existing
            orm_screenshot = OrmScreenshot.objects.get(id=screenshot.id)
            orm_screenshot.path = screenshot.path
            orm_screenshot.timestamp = screenshot.timestamp
            orm_screenshot.width = screenshot.width
            orm_screenshot.height = screenshot.height
            orm_screenshot.save()
        except OrmScreenshot.DoesNotExist:
            # Create new
            OrmScreenshot.objects.create(
                id=screenshot.id,
                media_id=screenshot.media_luid,
                path=screenshot.path,
                timestamp=screenshot.timestamp,
                width=screenshot.width,
                height=screenshot.height
            )
    
    @transaction.atomic
    def delete(self, id: str) -> bool:
        """Delete a screenshot."""
        try:
            OrmScreenshot.objects.get(id=id).delete()
            return True
        except OrmScreenshot.DoesNotExist:
            return False
    
    def _orm_to_domain(self, orm_screenshot: OrmScreenshot) -> Screenshot:
        """Convert ORM model to domain model."""
        return Screenshot(
            id=orm_screenshot.id,
            media_luid=orm_screenshot.media_id,
            path=orm_screenshot.path,
            timestamp=orm_screenshot.timestamp,
            width=orm_screenshot.width,
            height=orm_screenshot.height,
            created_at=orm_screenshot.created_at
        )


# Singleton instances
_media_repository = None
_screenshot_repository = None


def get_media_repository() -> MediaRepository:
    """Get or create a MediaRepository instance."""
    global _media_repository
    if _media_repository is None:
        _media_repository = MediaRepository()
    return _media_repository


def get_screenshot_repository() -> ScreenshotRepository:
    """Get or create a ScreenshotRepository instance."""
    global _screenshot_repository
    if _screenshot_repository is None:
        _screenshot_repository = ScreenshotRepository()
    return _screenshot_repository
