"""Application service for gRPC operations coordination."""
import asyncio
import logging
from typing import List, Optional

from django.conf import settings

from ..domain.models import Media, MediaStatus
from ..infrastructure.repositories import get_media_repository
from ..infrastructure.grpc.client import MediaGrpcClient

logger = logging.getLogger(__name__)


class MediaGrpcService:
    """Orchestrates gRPC operations for media management."""

    def __init__(self):
        self.media_repository = get_media_repository()
        self.grpc_client: Optional[MediaGrpcClient] = None
        self._connected = False

    async def initialize(self, peer_id: str) -> bool:
        """Initialize gRPC service with peer ID."""
        try:
            self.grpc_client = MediaGrpcClient(peer_id)
            self._connected = await self.grpc_client.connect()
            
            if self._connected:
                logger.info("gRPC service initialized successfully")
                # Announce existing catalog on startup
                await self._announce_existing_catalog()
            else:
                logger.warning("Failed to connect to edge service")
                
            return self._connected

        except Exception as e:
            logger.error(f"Error initializing gRPC service: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown gRPC service."""
        if self.grpc_client:
            await self.grpc_client.disconnect()
            self._connected = False

    async def announce_new_media(self, media_list: List[Media]) -> bool:
        """Announce new media files to edge service."""
        if not self._connected or not self.grpc_client:
            logger.warning("gRPC client not connected")
            return False

        try:
            # Filter for media without catalog IDs
            new_media = [m for m in media_list if not m.catalog_id and m.relative_path]
            
            if not new_media:
                return True

            # Announce files and get catalog IDs
            catalog_ids = await self.grpc_client.announce_files(new_media)
            
            # Update media with catalog IDs
            for i, media in enumerate(new_media):
                if i < len(catalog_ids):
                    media.catalog_id = catalog_ids[i]
                    self.media_repository.save(media)

            logger.info(f"Announced {len(new_media)} new media files")
            
            # Update full catalog announcement
            await self._announce_existing_catalog()
            return True

        except Exception as e:
            logger.error(f"Error announcing new media: {e}")
            return False

    async def update_catalog_status(self, media: Media) -> bool:
        """Update catalog status for a single media file."""
        if not self._connected or not self.grpc_client:
            return False

        try:
            if media.status == MediaStatus.READY and not media.catalog_id:
                # Announce single file
                catalog_ids = await self.grpc_client.announce_files([media])
                if catalog_ids:
                    media.catalog_id = catalog_ids[0]
                    self.media_repository.save(media)
                    await self._announce_existing_catalog()
                    return True

        except Exception as e:
            logger.error(f"Error updating catalog status: {e}")

        return False

    async def _announce_existing_catalog(self) -> None:
        """Announce all existing catalog IDs."""
        if not self._connected or not self.grpc_client:
            return

        try:
            ready_media = self.media_repository.get_by_status(MediaStatus.READY)
            catalog_ids = [m.catalog_id for m in ready_media if m.catalog_id]
            
            if catalog_ids:
                await self.grpc_client.announce_catalog(catalog_ids)
                logger.debug(f"Announced catalog with {len(catalog_ids)} items")

        except Exception as e:
            logger.error(f"Error announcing existing catalog: {e}")

    def is_connected(self) -> bool:
        """Check if gRPC client is connected."""
        return self._connected


# Singleton instance
_grpc_service = None


def get_media_grpc_service() -> MediaGrpcService:
    """Get or create MediaGrpcService instance."""
    global _grpc_service
    if _grpc_service is None:
        _grpc_service = MediaGrpcService()
    return _grpc_service
