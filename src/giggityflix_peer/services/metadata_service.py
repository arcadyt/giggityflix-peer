import logging
from pathlib import Path

from giggityflix_peer.models.media import MediaFile, MediaType
from giggityflix_peer.services.db_service import db_service
from giggityflix_peer.utils.video_file_utils import VideoReader

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for extracting and managing media file metadata."""

    async def extract_and_update_metadata(self, media_file: MediaFile) -> bool:
        """
        Extract metadata from a media file and update the database.

        Args:
            media_file: The media file to extract metadata from

        Returns:
            True if metadata was successfully extracted and updated, False otherwise
        """
        if media_file.media_type != MediaType.VIDEO:
            logger.debug(f"Metadata extraction not supported for {media_file.media_type}")
            return False

        path = media_file.path
        if not Path(path).exists():
            logger.error(f"File does not exist: {path}")
            return False

        try:
            # Extract metadata
            metadata = VideoReader.extract_metadata(str(path))
            if not metadata:
                logger.error(f"Failed to extract metadata from {path}")
                return False

            # Update media file with metadata
            media_file.duration_seconds = float(
                metadata.frames) / metadata.frame_rate if metadata.frames > 0 and metadata.frame_rate > 0 else None
            media_file.width = metadata.width
            media_file.height = metadata.height
            media_file.codec = metadata.codec
            media_file.bitrate = metadata.bit_rate
            media_file.framerate = metadata.frame_rate

            # Update in database
            await db_service.update_media_file(media_file)

            logger.info(f"Updated metadata for {path}")
            return True

        except Exception as e:
            logger.error(f"Error extracting and updating metadata for {path}: {e}")
            return False


# Create a singleton service instance
metadata_service = MetadataService()