import asyncio
import logging
import os
import signal
import uuid
from pathlib import Path

from giggityflix_peer.scanner.media_scanner_updated import MediaScanner

from giggityflix_peer.old_api.router import api_router
from giggityflix_peer.old_api.server import api_server
from giggityflix_peer.config import config
from giggityflix_peer.old_db.sqlite import db
# Import resource management components
from giggityflix_peer.di import container
from giggityflix_peer.old_resource_mgmt.resource_pool import ResourcePoolManager, MetricsCollector
from giggityflix_peer.apps.media.fixme_services import stream_service
from giggityflix_peer.old_services.config_service import config_service
from giggityflix_peer.old_services.db_service import db_service
from giggityflix_peer.apps.media.fixme_grpc import edge_client

logger = logging.getLogger(__name__)


class PeerApp:
    """Main application class for the peer service."""

    def __init__(self):
        """Initialize the peer application."""
        # Generate a peer ID if not provided
        self.peer_id = config.peer.peer_id
        if not self.peer_id and config.peer.auto_generate_id:
            self.peer_id = str(uuid.uuid4())
            logger.info(f"Generated peer ID: {self.peer_id}")

        # Create data and media directories
        self.data_dir = Path(config.peer.data_dir)
        os.makedirs(self.data_dir, exist_ok=True)

        # Initialize components
        self.media_scanner = MediaScanner(db_service)

        # Control flags
        self._running = False
        self._stop_event = asyncio.Event()

        # Initialize resource management
        self._init_resource_management()

    def _init_resource_management(self):
        """Initialize resource management components."""
        # Initialize metrics collector
        metrics_collector = MetricsCollector(
            enabled=True,
            logger=lambda msg: logger.debug(msg)
        )

        # Initialize resource pool manager
        resource_manager = ResourcePoolManager(
            config=config.resource,
            metrics_collector=metrics_collector
        )

        # Register in DI container
        container.register(ResourcePoolManager, resource_manager)

    async def start(self) -> None:
        """Start the peer application."""
        if self._running:
            logger.warning("Peer application is already running")
            return

        logger.info("Starting peer application")
        self._running = True

        # Initialize the database
        await db.initialize()

        # Initialize configuration service
        await config_service.initialize()

        # Connect to the Edge Service
        edge_connected = await edge_client.connect()
        if not edge_connected:
            logger.warning("Failed to connect to Edge Service, continuing in offline mode")

        # Start the media scanner
        await self.media_scanner.start()

        # Start the stream service
        await stream_service.start()

        # Register resource management API routes
        api_server.app.include_router(api_router)

        # Start the API server
        await api_server.start()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.stop(s)))

        logger.info("Peer application started")

    async def stop(self, sig=None) -> None:
        """Stop the peer application."""
        if not self._running:
            return

        if sig:
            logger.info(f"Received signal {sig.name}, shutting down")
        else:
            logger.info("Shutting down peer application")

        self._running = False
        self._stop_event.set()

        # Stop the API server
        await api_server.stop()

        # Stop the stream service
        await stream_service.stop()

        # Stop the media scanner
        await self.media_scanner.stop()

        # Disconnect from the Edge Service
        await edge_client.disconnect()

        # Clean up resource management
        resource_manager = container.resolve(ResourcePoolManager)
        resource_manager.shutdown()

        # Close the database
        await db.close()

        logger.info("Peer application stopped")

    async def scan_media(self) -> None:
        """Trigger a media scan."""
        if not self._running:
            logger.warning("Peer application is not running")
            return

        await self.media_scanner.scan_now()

    async def update_catalog(self) -> None:
        """Update the catalog with the Edge Service."""
        if not self._running:
            logger.warning("Peer application is not running")
            return

        # Get all media files from the database
        media_files = await db_service.get_all_media_files()

        # Update the catalog with the Edge Service
        if media_files:
            logger.info(f"Updating catalog with {len(media_files)} media files")
            if await edge_client.update_catalog(media_files):
                # Update the catalog IDs in the database
                for media_file in media_files:
                    if media_file.catalog_id:
                        await db_service.update_media_catalog_id(media_file.luid, media_file.catalog_id)
        else:
            logger.info("No media files to update in catalog")

    def is_running(self) -> bool:
        """Check if the peer application is running."""
        return self._running

    async def wait_for_stop(self) -> None:
        """Wait for the application to stop."""
        await self._stop_event.wait()


# Create a singleton application instance
peer_app = PeerApp()
