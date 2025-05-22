"""Main peer service coordinating all components using Django framework."""
import asyncio
import logging
import uuid
from typing import Optional

from giggityflix_peer.apps.configuration import services as config_service
from giggityflix_peer.apps.media.application.media_service import get_media_service
from giggityflix_peer.di import container

logger = logging.getLogger(__name__)


class PeerService:
    """Main peer service using Django framework and proper DI."""

    def __init__(self):
        self.peer_id: Optional[str] = None
        self.media_service = get_media_service()
        self._initialized = False
        self._running = False
        self._stop_event = asyncio.Event()

    async def initialize(self) -> bool:
        """Initialize peer service with proper dependency order."""
        if self._initialized:
            return True

        try:
            logger.info("Initializing Giggityflix Peer Service...")

            # Get or generate peer ID from configuration
            self.peer_id = await config_service.get('peer_id', '')
            if not self.peer_id:
                self.peer_id = str(uuid.uuid4())
                await config_service.set('peer_id', self.peer_id)
                logger.info(f"Generated new peer ID: {self.peer_id}")
            else:
                logger.info(f"Using existing peer ID: {self.peer_id}")

            # Initialize media service
            media_initialized = await self.media_service.initialize(self.peer_id)
            if not media_initialized:
                logger.error("Failed to initialize media service")
                return False

            # Register in DI container
            container.register(PeerService, self)

            self._initialized = True
            logger.info("✓ Peer service initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing peer service: {e}")
            return False

    async def start(self) -> bool:
        """Start peer service."""
        if not self._initialized:
            logger.error("Peer service not initialized")
            return False

        if self._running:
            logger.warning("Peer service already running")
            return True

        try:
            logger.info("Starting peer service...")
            self._running = True

            # Perform initial media scan
            scan_result = await self.media_service.scan_media_directories()
            logger.info(f"Initial scan: {scan_result}")

            logger.info("✓ Peer service started successfully")
            return True

        except Exception as e:
            logger.error(f"Error starting peer service: {e}")
            self._running = False
            return False

    async def stop(self) -> None:
        """Stop peer service."""
        if not self._running:
            return

        try:
            logger.info("Stopping peer service...")
            self._running = False
            self._stop_event.set()

            await self.media_service.shutdown()

            logger.info("✓ Peer service stopped")

        except Exception as e:
            logger.error(f"Error stopping peer service: {e}")

    async def trigger_media_scan(self) -> dict:
        """Trigger a media scan manually."""
        if not self._running:
            logger.warning("Peer service not running")
            return {'total': 0, 'new': 0, 'deleted': 0}

        return await self.media_service.scan_media_directories()

    def is_running(self) -> bool:
        """Check if peer service is running."""
        return self._running

    def is_grpc_connected(self) -> bool:
        """Check if gRPC connection is active."""
        return self.media_service.is_grpc_connected()

    async def wait_for_stop(self) -> None:
        """Wait for service to stop."""
        await self._stop_event.wait()


# Singleton instance
_peer_service = None


def get_peer_service() -> PeerService:
    """Get or create PeerService instance."""
    global _peer_service
    if _peer_service is None:
        _peer_service = PeerService()
    return _peer_service
