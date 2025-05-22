"""gRPC message handlers for media operations."""
import logging
from pathlib import Path
from typing import Optional

from giggityflix_peer.apps.configuration import services as config_service
from ...infrastructure.repositories import get_media_repository
from ...domain.models import MediaStatus

logger = logging.getLogger(__name__)

# Try to import gRPC components, handle gracefully if missing
try:
    from giggityflix_grpc_peer import (
        EdgeMessage, PeerMessage,
        file_operations, catalog, commons
    )
    GRPC_AVAILABLE = True
except ImportError as e:
    logger.warning(f"gRPC protobuf modules not available: {e}")
    GRPC_AVAILABLE = False
    # Create dummy classes to prevent import errors
    class EdgeMessage: pass
    class PeerMessage: pass
    class file_operations: pass
    class catalog: pass
    class commons: pass


class MediaGrpcHandlers:
    """Handles gRPC messages from edge service."""

    def __init__(self):
        self.media_repository = get_media_repository()
        # Only import screenshot service if available to avoid circular imports
        self.screenshot_service = None

    async def handle_message(self, message) -> Optional:
        """Process message from edge using strategy pattern."""
        if not GRPC_AVAILABLE:
            logger.warning("gRPC not available, cannot handle message")
            return None
            
        # Import screenshot service lazily to avoid circular imports
        if self.screenshot_service is None:
            try:
                from ...application.screenshot_service import get_screenshot_service
                self.screenshot_service = get_screenshot_service()
            except ImportError:
                logger.warning("Screenshot service not available")
                
        logger.debug(f"Received message type: {message.WhichOneof('payload')}")

        if message.HasField('file_delete_request'):
            return await self._handle_file_delete_request(message)
        elif message.HasField('file_hash_request'):
            return await self._handle_file_hash_request(message)
        elif message.HasField('file_remap_request'):
            return await self._handle_file_remap_request(message)
        elif message.HasField('batch_file_offer_response'):
            return await self._handle_batch_file_offer_response(message)
        elif message.HasField('catalog_announcement_request'):
            return await self._handle_catalog_announcement_request(message)
        elif message.HasField('screenshot_capture_request'):
            return await self._handle_screenshot_capture_request(message)

        logger.warning(f"Unknown message type: {message.WhichOneof('payload')}")
        return None

    async def _handle_file_delete_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handle file delete request."""
        request = message.file_delete_request
        request_id = message.request_id
        catalog_ids = list(request.catalog_ids)

        logger.info(f"Processing file delete request for {len(catalog_ids)} files")

        for catalog_id in catalog_ids:
            try:
                media = self.media_repository.get_by_catalog_id(catalog_id)
                if media:
                    media.mark_deleted()
                    self.media_repository.save(media)
                    logger.info(f"Marked file {catalog_id} as deleted: {media.path}")
                else:
                    logger.warning(f"File with catalog ID {catalog_id} not found")

                response = file_operations.FileDeleteResponse(
                    catalog_id=catalog_id,
                    success=media is not None
                )
                
                if media is None:
                    response.error = commons.CatalogErrorReason.BAD_CATALOG_ID

                return PeerMessage(
                    request_id=request_id,
                    file_delete_response=response
                )

            except Exception as e:
                logger.error(f"Error deleting file {catalog_id}: {e}")
                response = file_operations.FileDeleteResponse(
                    catalog_id=catalog_id,
                    success=False,
                    error=commons.CatalogErrorReason.PERMISSION_DENIED
                )
                return PeerMessage(request_id=request_id, file_delete_response=response)

        return None

    async def _handle_file_hash_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handle file hash request."""
        request = message.file_hash_request
        request_id = message.request_id
        catalog_id = request.catalog_id
        hash_types = list(request.hash_types)

        logger.info(f"Processing file hash request for {catalog_id} with hash types: {hash_types}")

        try:
            media = self.media_repository.get_by_catalog_id(catalog_id)
            if not media:
                response = file_operations.FileHashResponse(
                    catalog_id=catalog_id,
                    hashes={},
                    success=False,
                    error=commons.CatalogErrorReason.BAD_CATALOG_ID
                )
                return PeerMessage(request_id=request_id, file_hash_response=response)

            if not media.exists():
                response = file_operations.FileHashResponse(
                    catalog_id=catalog_id,
                    hashes={},
                    success=False,
                    error=commons.CatalogErrorReason.FILE_GONE
                )
                return PeerMessage(request_id=request_id, file_hash_response=response)

            # Return existing hashes
            hashes = {}
            for hash_type in hash_types:
                if hash_type in media.hashes:
                    hashes[hash_type] = media.hashes[hash_type]

            response = file_operations.FileHashResponse(
                catalog_id=catalog_id,
                hashes=hashes,
                success=True
            )
            return PeerMessage(request_id=request_id, file_hash_response=response)

        except Exception as e:
            logger.error(f"Error processing hash request for {catalog_id}: {e}")
            response = file_operations.FileHashResponse(
                catalog_id=catalog_id,
                hashes={},
                success=False,
                error=commons.CatalogErrorReason.PERMISSION_DENIED
            )
            return PeerMessage(request_id=request_id, file_hash_response=response)

    async def _handle_file_remap_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handle file remap request."""
        request = message.file_remap_request
        old_catalog_id = request.old_catalog_id
        new_catalog_id = request.new_catalog_id

        logger.info(f"Processing file remap request: {old_catalog_id} -> {new_catalog_id}")

        try:
            media = self.media_repository.get_by_catalog_id(old_catalog_id)
            if media:
                media.catalog_id = new_catalog_id
                self.media_repository.save(media)
                logger.info(f"Remapped catalog ID: {old_catalog_id} -> {new_catalog_id}")

        except Exception as e:
            logger.error(f"Error remapping catalog ID: {e}")

        return None

    async def _handle_batch_file_offer_response(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handle batch file offer response."""
        response = message.batch_file_offer_response
        files = list(response.files)

        logger.info(f"Processing batch file offer response with {len(files)} files")

        for file_info in files:
            try:
                # Find media by relative path
                all_media = self.media_repository.get_all()
                media = next((m for m in all_media if m.relative_path == file_info.relative_path), None)

                if media:
                    media.catalog_id = file_info.catalog_id
                    self.media_repository.save(media)
                    logger.info(f"Updated catalog ID for {file_info.relative_path}: {file_info.catalog_id}")

            except Exception as e:
                logger.error(f"Error updating catalog ID for {file_info.relative_path}: {e}")

        return None

    async def _handle_catalog_announcement_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handle catalog announcement request."""
        request_id = message.request_id
        logger.info("Processing catalog announcement request")

        try:
            media_list = self.media_repository.get_by_status(MediaStatus.READY)
            catalog_ids = [m.catalog_id for m in media_list if m.catalog_id]

            response = catalog.CatalogAnnouncementResponse(catalog_ids=catalog_ids)
            return PeerMessage(request_id=request_id, catalog_announcement=response)

        except Exception as e:
            logger.error(f"Error processing catalog announcement request: {e}")
            return PeerMessage(
                request_id=request_id,
                catalog_announcement=catalog.CatalogAnnouncementResponse(catalog_ids=[])
            )

    async def _handle_screenshot_capture_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handle screenshot capture request."""
        request = message.screenshot_capture_request
        request_id = message.request_id
        catalog_id = request.catalog_id
        quantity = request.quantity
        upload_token = request.upload_token
        upload_endpoint = request.upload_endpoint

        logger.info(f"Processing screenshot capture request for {catalog_id}")

        try:
            media = self.media_repository.get_by_catalog_id(catalog_id)
            if not media:
                logger.warning(f"File with catalog ID {catalog_id} not found")
                return None

            # Capture screenshots
            screenshots = await self.screenshot_service.capture_for_media(media.luid, quantity)
            
            if screenshots and upload_endpoint and upload_token:
                # Extract screenshot data for upload
                screenshot_data = []
                for screenshot in screenshots:
                    with open(screenshot.path, 'rb') as f:
                        screenshot_data.append(f.read())
                
                # Upload screenshots
                success = await self.screenshot_service.upload_screenshots(
                    screenshot_data, upload_endpoint, upload_token
                )
                
                if success:
                    logger.info(f"Successfully captured and uploaded {len(screenshots)} screenshots for {catalog_id}")
                else:
                    logger.warning(f"Failed to upload screenshots for {catalog_id}")
            else:
                logger.info(f"Captured {len(screenshots)} screenshots for {catalog_id} (no upload requested)")

        except Exception as e:
            logger.error(f"Error processing screenshot request for {catalog_id}: {e}")

        return None
