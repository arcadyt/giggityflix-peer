"""Service for extracting and managing media file metadata."""
import logging
from pathlib import Path
from typing import Optional

from ..domain.models import Media, MediaType
from ..infrastructure.repositories import get_media_repository
from ..video_file_utils import VideoReader

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for extracting and managing media file metadata."""

    def __init__(self):
        self.media_repository = get_media_repository()

    def extract_and_update_metadata(self, media: Media) -> bool:
        """Extract metadata from media file and update repository."""
        if media.media_type != MediaType.VIDEO:
            logger.debug(f"Metadata extraction not supported for {media.media_type}")
            return False

        if not media.exists():
            logger.error(f"File does not exist: {media.path}")
            return False

        try:
            metadata = VideoReader.extract_metadata(media.path)
            if not metadata:
                logger.error(f"Failed to extract metadata from {media.path}")
                return False

            # Update media with metadata
            media.duration_seconds = (
                float(metadata.frames) / metadata.frame_rate 
                if metadata.frames > 0 and metadata.frame_rate > 0 
                else None
            )
            media.width = metadata.width
            media.height = metadata.height
            media.codec = metadata.codec
            media.bitrate = metadata.bit_rate
            media.framerate = metadata.frame_rate

            # Save to repository
            self.media_repository.save(media)

            logger.info(f"Updated metadata for {media.path}")
            return True

        except Exception as e:
            logger.error(f"Error extracting and updating metadata for {media.path}: {e}")
            return False

    def update_media_metadata_batch(self, media_list: list[Media]) -> int:
        """Update metadata for multiple media files."""
        updated_count = 0
        
        for media in media_list:
            if self.extract_and_update_metadata(media):
                updated_count += 1
                
        logger.info(f"Updated metadata for {updated_count}/{len(media_list)} media files")
        return updated_count


# Singleton instance
_metadata_service = None


def get_metadata_service() -> MetadataService:
    """Get or create MetadataService instance."""
    global _metadata_service
    if _metadata_service is None:
        _metadata_service = MetadataService()
    return _metadata_service
