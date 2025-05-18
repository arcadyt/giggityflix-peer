import logging
from pathlib import Path
from typing import Optional

from giggityflix_grpc_peer import (
    EdgeMessage, PeerMessage,
    file_operations, catalog, commons
)

from giggityflix_peer.models.media import MediaStatus
from giggityflix_peer.services.db_service import db_service
from giggityflix_peer.services.screenshot_service import screenshot_service, ScreenshotUploader

logger = logging.getLogger(__name__)


class EdgeMessageHandler:
    """Handles messages from edge service."""

    async def handle_message(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Processes message from edge using strategy pattern."""
        logger.debug(f"Received message type: {message.WhichOneof('payload')}")

        # Select handler based on message type
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
        """
        Handles file delete request.
        
        Deletes files with the specified catalog IDs and returns a response
        indicating success or failure.
        """
        request = message.file_delete_request
        request_id = message.request_id
        catalog_ids = list(request.catalog_ids)

        logger.info(f"Processing file delete request for {len(catalog_ids)} files")

        # Process each catalog ID
        responses = []
        for catalog_id in catalog_ids:
            success = True
            error_reason = None

            try:
                # Get the media file by catalog ID
                media_file = await db_service.get_media_file_by_catalog_id(catalog_id)
                if not media_file:
                    logger.warning(f"File with catalog ID {catalog_id} not found")
                    success = False
                    error_reason = commons.CatalogErrorReason.BAD_CATALOG_ID
                    continue

                # Mark as deleted in the database
                media_file.status = MediaStatus.DELETED
                await db_service.update_media_file(media_file)
                logger.info(f"Marked file {catalog_id} as deleted: {media_file.path}")

            except Exception as e:
                logger.error(f"Error deleting file {catalog_id}: {e}")
                success = False
                error_reason = commons.CatalogErrorReason.PERMISSION_DENIED

            # Create response for this catalog ID
            response = file_operations.FileDeleteResponse(
                catalog_id=catalog_id,
                success=success
            )
            if error_reason is not None:
                response.error = error_reason

            responses.append(response)

        # Return the first response (if any)
        if responses:
            return PeerMessage(
                request_id=request_id,
                file_delete_response=responses[0]
            )

        return None

    async def _handle_file_hash_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """
        Handles file hash request.
        
        Computes requested hash types for the specified catalog ID and
        returns the results.
        """
        request = message.file_hash_request
        request_id = message.request_id
        catalog_id = request.catalog_id
        hash_types = list(request.hash_types)

        logger.info(f"Processing file hash request for {catalog_id} with hash types: {hash_types}")

        success = True
        error_reason = None
        hashes = {}

        try:
            # Get the media file by catalog ID
            media_file = await db_service.get_media_file_by_catalog_id(catalog_id)
            if not media_file:
                logger.warning(f"File with catalog ID {catalog_id} not found")
                success = False
                error_reason = commons.CatalogErrorReason.BAD_CATALOG_ID
            elif not Path(media_file.path).exists():
                logger.warning(f"File {media_file.path} no longer exists")
                success = False
                error_reason = commons.CatalogErrorReason.FILE_GONE
            else:
                # Compute requested hashes
                from giggityflix_peer.scanner.media_scanner_updated import calculate_file_hash

                for hash_type in hash_types:
                    try:
                        if hash_type in media_file.hashes:
                            # Use existing hash if available
                            hashes[hash_type] = media_file.hashes[hash_type]
                        else:
                            # Compute hash
                            hash_value = await calculate_file_hash(media_file.path, hash_type)
                            hashes[hash_type] = hash_value

                            # Update media file with new hash
                            media_file.hashes[hash_type] = hash_value
                            await db_service.update_media_file(media_file)

                    except Exception as e:
                        logger.error(f"Error computing {hash_type} hash for {catalog_id}: {e}")
                        # Continue with other hash types

        except Exception as e:
            logger.error(f"Error processing hash request for {catalog_id}: {e}")
            success = False
            error_reason = commons.CatalogErrorReason.PERMISSION_DENIED

        # Create response
        response = file_operations.FileHashResponse(
            catalog_id=catalog_id,
            hashes=hashes,
            success=success
        )
        if error_reason is not None:
            response.error = error_reason

        return PeerMessage(
            request_id=request_id,
            file_hash_response=response
        )

    async def _handle_file_remap_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """
        Handles file remap request.
        
        Updates the catalog ID of a file from old_catalog_id to new_catalog_id.
        """
        request = message.file_remap_request
        request_id = message.request_id
        old_catalog_id = request.old_catalog_id
        new_catalog_id = request.new_catalog_id

        logger.info(f"Processing file remap request: {old_catalog_id} -> {new_catalog_id}")

        success = True
        error_reason = None

        try:
            # Get the media file by old catalog ID
            media_file = await db_service.get_media_file_by_catalog_id(old_catalog_id)
            if not media_file:
                logger.warning(f"File with catalog ID {old_catalog_id} not found")
                success = False
                error_reason = commons.CatalogErrorReason.BAD_CATALOG_ID
            else:
                # Update catalog ID
                media_file.catalog_id = new_catalog_id
                await db_service.update_media_file(media_file)
                logger.info(f"Remapped catalog ID: {old_catalog_id} -> {new_catalog_id}")

        except Exception as e:
            logger.error(f"Error remapping catalog ID: {e}")
            success = False
            error_reason = commons.CatalogErrorReason.PERMISSION_DENIED

        # Create file remap response (if expected)
        # This is not defined in the proto files, so we can return None
        return None

    async def _handle_batch_file_offer_response(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """
        Handles batch file offer response.
        
        Updates local media files with catalog IDs assigned by the edge service.
        """
        request_id = message.request_id
        response = message.batch_file_offer_response
        files = list(response.files)

        logger.info(f"Processing batch file offer response with {len(files)} files")

        for file_info in files:
            relative_path = file_info.relative_path
            catalog_id = file_info.catalog_id

            try:
                # Find media file by relative path
                all_media = await db_service.get_all_media_files()
                media_file = next((m for m in all_media if m.relative_path == relative_path), None)

                if media_file:
                    # Update catalog ID
                    await db_service.update_media_catalog_id(media_file.luid, catalog_id)
                    logger.info(f"Updated catalog ID for {relative_path}: {catalog_id}")
                else:
                    logger.warning(f"Could not find media file with relative path: {relative_path}")

            except Exception as e:
                logger.error(f"Error updating catalog ID for {relative_path}: {e}")

        # No response needed for this message type
        return None

    async def _handle_catalog_announcement_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """
        Handles catalog announcement request.
        
        Responds with a list of all catalog IDs known to this peer.
        """
        request_id = message.request_id

        logger.info("Processing catalog announcement request")

        try:
            # Get all media files with catalog IDs
            media_files = await db_service.get_all_media_files()
            catalog_ids = [
                file.catalog_id for file in media_files
                if file.catalog_id and file.status != MediaStatus.DELETED
            ]

            # Create response
            response = catalog.CatalogAnnouncementResponse(
                catalog_ids=catalog_ids
            )

            return PeerMessage(
                request_id=request_id,
                catalog_announcement=response
            )

        except Exception as e:
            logger.error(f"Error processing catalog announcement request: {e}")

            # Send empty response on error
            return PeerMessage(
                request_id=request_id,
                catalog_announcement=catalog.CatalogAnnouncementResponse(
                    catalog_ids=[]
                )
            )

    async def _handle_screenshot_capture_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """
        Handles screenshot capture request.

        Captures screenshots for the specified catalog ID and uploads them
        to the provided endpoint.
        """
        request = message.screenshot_capture_request
        request_id = message.request_id
        catalog_id = request.catalog_id
        quantity = request.quantity
        upload_token = request.upload_token
        upload_endpoint = request.upload_endpoint

        logger.info(f"Processing screenshot capture request for {catalog_id}")

        try:
            # Get the media file by catalog ID
            media_file = await db_service.get_media_file_by_catalog_id(catalog_id)
            if not media_file:
                logger.warning(f"File with catalog ID {catalog_id} not found")
                return None

            # Capture screenshots
            screenshot_data = await screenshot_service.capture_screenshots(media_file, quantity)
            if not screenshot_data:
                logger.warning(f"Failed to capture screenshots for {catalog_id}")
                return None

            # Upload screenshots
            success = await ScreenshotUploader.upload_screenshots(
                screenshot_data, upload_endpoint, upload_token
            )

            logger.info(f"Screenshot upload {'succeeded' if success else 'failed'} for {catalog_id}")

        except Exception as e:
            logger.error(f"Error processing screenshot request for {catalog_id}: {e}")

        # No response message defined for screenshot requests
        return None
