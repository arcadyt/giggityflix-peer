import logging
from typing import Optional

from giggityflix_grpc_peer import (
    EdgeMessage, PeerMessage,
    file_operations, media
)

logger = logging.getLogger(__name__)


class EdgeMessageHandler:
    """Handles messages from edge service."""

    async def handle_message(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Processes message from edge."""
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

        logger.warning(f"Unknown message type")
        return None

    async def _handle_file_delete_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handles file delete request."""
        # Implementation placeholder
        return None

    async def _handle_file_hash_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handles file hash request."""
        # Implementation placeholder
        return None

    async def _handle_file_remap_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handles file remap request."""
        # Implementation placeholder
        return None

    async def _handle_batch_file_offer_response(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handles batch file offer response."""
        # Implementation placeholder
        return None

    async def _handle_catalog_announcement_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handles catalog announcement request."""
        # Implementation placeholder
        return None

    async def _handle_screenshot_capture_request(self, message: EdgeMessage) -> Optional[PeerMessage]:
        """Handles screenshot capture request."""
        # Implementation placeholder
        return None