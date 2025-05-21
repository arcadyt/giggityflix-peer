import logging
from typing import List, Optional, Tuple

from giggityflix_peer.config import config
from giggityflix_peer.grpc.client import EdgeClient as GrpcEdgeClient
from giggityflix_peer.grpc.handlers import EdgeMessageHandler
from giggityflix_peer.models.media import MediaFile
from giggityflix_peer.old_services.db_service import db_service

logger = logging.getLogger(__name__)


class EdgeClient:
    """
    Main edge client service that interfaces with the gRPC client.
    
    This service manages the connection to the edge service and provides
    high-level methods for interacting with the edge service.
    """

    def __init__(self, peer_id: str):
        """Initialize the edge client service."""
        self.peer_id = peer_id
        self._client = None
        self._initialized = False

    async def connect(self) -> bool:
        """
        Connect to the edge service.
        
        Returns:
            True if connected successfully, False otherwise
        """
        if not self._initialized:
            # Create handler
            handler = EdgeMessageHandler()

            # Create gRPC client
            self._client = GrpcEdgeClient(self.peer_id, handler)
            self._initialized = True

        # Start the client
        return await self._client.start()

    async def disconnect(self) -> None:
        """Disconnect from the edge service."""
        if self._client:
            await self._client.stop()

    async def update_catalog(self, media_files: List[MediaFile]) -> bool:
        """
        Update catalog information with the edge service.
        
        This method sends all media files to the edge service to get catalog IDs,
        then updates the local database with the assigned IDs.
        
        Args:
            media_files: List of media files to update
            
        Returns:
            True if the update was successful, False otherwise
        """
        if not self._client:
            logger.error("Edge client not initialized")
            return False

        try:
            # Filter out deleted files and files with no relative path
            valid_files = [f for f in media_files if f.relative_path and not f.status.value == "deleted"]

            if not valid_files:
                logger.warning("No valid files to announce")
                return False

            # Announce files
            logger.info(f"Announcing {len(valid_files)} files to edge service")
            catalog_ids = await self._client.announce_files(valid_files)

            if not catalog_ids:
                logger.warning("No catalog IDs received from edge service")
                return False

            # Update local database with catalog IDs
            updated_count = 0
            for media_file in valid_files:
                if media_file.catalog_id:
                    await db_service.update_media_catalog_id(media_file.luid, media_file.catalog_id)
                    updated_count += 1

            logger.info(f"Updated {updated_count} files with catalog IDs")

            # Announce full catalog
            all_media = await db_service.get_all_media_files()
            catalog_ids = [f.catalog_id for f in all_media if f.catalog_id and not f.status.value == "deleted"]

            if catalog_ids:
                await self._client.announce_catalog(catalog_ids)

            return True

        except Exception as e:
            logger.error(f"Error updating catalog: {e}")
            return False

    async def create_stream_session(self, media_luid: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Create a streaming session for a media file.
        
        Args:
            media_luid: Local unique ID of the media file
            
        Returns:
            Tuple of (session_id, sdp_offer) or (None, None) if error
        """
        if not self._client:
            logger.error("Edge client not initialized")
            return None, None

        try:
            # Get media file
            media_file = await db_service.get_media_file(media_luid)
            if not media_file:
                logger.error(f"Media file not found: {media_luid}")
                return None, None

            # Check if media file has catalog ID
            if not media_file.catalog_id:
                logger.error(f"Media file has no catalog ID: {media_luid}")
                return None, None

            # Create stream session
            return await self._client.create_stream_session(media_file.catalog_id)

        except Exception as e:
            logger.error(f"Error creating stream session: {e}")
            return None, None

    async def send_sdp_answer(self, session_id: str, sdp: str) -> bool:
        """
        Send SDP answer for a WebRTC session.
        
        Args:
            session_id: ID of the streaming session
            sdp: SDP answer
            
        Returns:
            True if successful, False otherwise
        """
        if not self._client:
            logger.error("Edge client not initialized")
            return False

        return await self._client.send_sdp_answer(session_id, sdp)

    async def send_ice_candidate(self, session_id: str, candidate: str,
                                 sdp_mid: str, sdp_mline_index: int) -> bool:
        """
        Send ICE candidate for a WebRTC session.
        
        Args:
            session_id: ID of the streaming session
            candidate: ICE candidate string
            sdp_mid: SDP mid attribute
            sdp_mline_index: SDP M-line index
            
        Returns:
            True if successful, False otherwise
        """
        if not self._client:
            logger.error("Edge client not initialized")
            return False

        return await self._client.send_ice_candidate(session_id, candidate, sdp_mid, sdp_mline_index)


# Create a singleton instance
edge_client = EdgeClient(config.peer.peer_id)
