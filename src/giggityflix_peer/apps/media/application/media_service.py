"""Main media application service coordinating all media operations."""
import logging
from typing import List, Optional, Dict, Any

from giggityflix_peer.apps.configuration import services as config_service
from giggityflix_peer.di import container

from ..domain.models import Media, MediaStatus, MediaType
from ..infrastructure.repositories import get_media_repository
from .grpc_service import get_media_grpc_service
from .scanner_service import get_media_scanner
from .stream_service import get_stream_service
from .metadata_service import get_metadata_service
from .screenshot_service import get_screenshot_service

logger = logging.getLogger(__name__)


class MediaApplicationService:
    """Main service coordinating media operations and dependencies."""

    def __init__(self):
        self.media_repository = get_media_repository()
        self.grpc_service = get_media_grpc_service()
        self.scanner_service = get_media_scanner()
        self.stream_service = get_stream_service()
        self.metadata_service = get_metadata_service()
        self.screenshot_service = get_screenshot_service()
        self._initialized = False

    async def initialize(self, peer_id: str) -> bool:
        """Initialize media service with all dependencies."""
        if self._initialized:
            return True

        try:
            logger.info("Initializing media application service...")

            # Initialize gRPC service first
            grpc_connected = await self.grpc_service.initialize(peer_id)
            if grpc_connected:
                logger.info("✓ gRPC service connected")
            else:
                logger.warning("⚠ gRPC service offline (continuing in standalone mode)")

            # Initialize stream service
            await self.stream_service.start()
            logger.info("✓ Stream service started")

            # Perform initial media scan
            await self._perform_initial_scan()

            # Register services in DI container
            self._register_services()

            self._initialized = True
            logger.info("✓ Media application service initialized")
            return True

        except Exception as e:
            logger.error(f"Error initializing media service: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown media application service."""
        if not self._initialized:
            return

        try:
            logger.info("Shutting down media application service...")

            await self.stream_service.stop()
            await self.grpc_service.shutdown()

            self._initialized = False
            logger.info("✓ Media application service shutdown complete")

        except Exception as e:
            logger.error(f"Error during media service shutdown: {e}")

    async def scan_media_directories(self) -> Dict[str, int]:
        """Trigger media directory scan and return results."""
        try:
            media_dirs = await config_service.get('media_dirs', [])
            media_extensions = await config_service.get('media_extensions', ['.mp4', '.mkv', '.avi', '.mov'])

            if not media_dirs:
                logger.warning("No media directories configured")
                return {'total': 0, 'new': 0, 'deleted': 0}

            total, new, deleted = await self.scanner_service.scan_directories(media_dirs, media_extensions)

            # Announce new media to gRPC if connected
            if new > 0 and self.grpc_service.is_connected():
                await self._announce_new_media()

            return {'total': total, 'new': new, 'deleted': deleted}

        except Exception as e:
            logger.error(f"Error scanning media directories: {e}")
            return {'total': 0, 'new': 0, 'deleted': 0}

    async def get_media_by_luid(self, luid: str) -> Optional[Media]:
        """Get media by local unique ID."""
        return self.media_repository.get_by_luid(luid)

    async def get_media_by_catalog_id(self, catalog_id: str) -> Optional[Media]:
        """Get media by catalog ID."""
        return self.media_repository.get_by_catalog_id(catalog_id)

    async def get_all_media(self) -> List[Media]:
        """Get all media files."""
        return self.media_repository.get_all()

    async def get_media_by_status(self, status: MediaStatus) -> List[Media]:
        """Get media files by status."""
        return self.media_repository.get_by_status(status)

    async def extract_metadata_for_media(self, luid: str) -> bool:
        """Extract and update metadata for a media file."""
        media = self.media_repository.get_by_luid(luid)
        if not media:
            return False

        return self.metadata_service.extract_and_update_metadata(media)

    async def capture_screenshots_for_media(self, luid: str, quantity: int = 3) -> List:
        """Capture screenshots for a media file."""
        return await self.screenshot_service.capture_for_media(luid, quantity)

    async def create_stream_session(self, luid: str) -> Optional[tuple]:
        """Create streaming session for media file."""
        return await self.stream_service.create_session(luid)

    async def handle_stream_answer(self, session_id: str, answer_sdp: str, answer_type: str) -> bool:
        """Handle WebRTC answer for streaming session."""
        return await self.stream_service.handle_answer(session_id, answer_sdp, answer_type)

    async def close_stream_session(self, session_id: str) -> bool:
        """Close streaming session."""
        return await self.stream_service.close_session(session_id)

    def is_grpc_connected(self) -> bool:
        """Check if gRPC service is connected."""
        return self.grpc_service.is_connected()

    async def _perform_initial_scan(self) -> None:
        """Perform initial media directory scan."""
        try:
            scan_result = await self.scan_media_directories()
            logger.info(f"Initial scan completed: {scan_result}")

        except Exception as e:
            logger.error(f"Error during initial scan: {e}")

    async def _announce_new_media(self) -> None:
        """Announce new media to gRPC service."""
        try:
            new_media = [m for m in self.media_repository.get_all() if not m.catalog_id]
            if new_media:
                success = await self.grpc_service.announce_new_media(new_media)
                if success:
                    logger.info(f"Announced {len(new_media)} new media files")

        except Exception as e:
            logger.error(f"Error announcing new media: {e}")

    def _register_services(self) -> None:
        """Register services in DI container."""
        try:
            # Register service instances
            container.register(MediaApplicationService, self)
            container.register(type(self.media_repository), self.media_repository)
            container.register(type(self.grpc_service), self.grpc_service)
            container.register(type(self.scanner_service), self.scanner_service)
            container.register(type(self.stream_service), self.stream_service)
            container.register(type(self.metadata_service), self.metadata_service)
            container.register(type(self.screenshot_service), self.screenshot_service)

            logger.debug("Services registered in DI container")

        except Exception as e:
            logger.error(f"Error registering services in DI container: {e}")


# Singleton instance
_media_service = None


def get_media_service() -> MediaApplicationService:
    """Get or create MediaApplicationService instance."""
    global _media_service
    if _media_service is None:
        _media_service = MediaApplicationService()
    return _media_service
