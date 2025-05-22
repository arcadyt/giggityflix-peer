"""Django management command to start the peer service."""
import asyncio
import logging
import os
import signal
import uuid
from typing import Optional

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from django.conf import settings

from ...application.grpc_service import get_media_grpc_service
from ...application.scanner_service import get_media_scanner
from ...application.stream_service import get_stream_service
from ...application.metadata_service import get_metadata_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Start the peer service with gRPC, media scanning, and streaming capabilities'

    def add_arguments(self, parser):
        parser.add_argument(
            '--peer-id',
            type=str,
            help='Unique identifier for this peer (auto-generated if not provided)'
        )
        parser.add_argument(
            '--media-dirs',
            nargs='+',
            help='Directories to scan for media files'
        )
        parser.add_argument(
            '--scan-interval',
            type=int,
            default=3600,
            help='Media scan interval in seconds (default: 3600)'
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        # Generate peer ID if not provided
        peer_id = options.get('peer_id') or getattr(settings, 'PEER_ID', None) or str(uuid.uuid4())
        media_dirs = options.get('media_dirs') or getattr(settings, 'MEDIA_DIRECTORIES', [])
        scan_interval = options.get('scan_interval')

        if not media_dirs:
            self.stdout.write(
                self.style.ERROR('No media directories specified. Set MEDIA_DIRECTORIES in settings or use --media-dirs')
            )
            return

        self.stdout.write(f'Starting peer service with ID: {peer_id}')
        self.stdout.write(f'Media directories: {", ".join(media_dirs)}')
        self.stdout.write(f'Scan interval: {scan_interval} seconds')

        # Run the async peer service
        try:
            asyncio.run(self._run_peer_service(peer_id, media_dirs, scan_interval))
        except KeyboardInterrupt:
            self.stdout.write('\nShutting down...')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error running peer service: {e}'))
            logger.exception("Peer service error")

    async def _run_peer_service(self, peer_id: str, media_dirs: list, scan_interval: int):
        """Run the peer service with all components."""
        # Get service instances
        grpc_service = get_media_grpc_service()
        scanner_service = get_media_scanner()
        stream_service = get_stream_service()
        metadata_service = get_metadata_service()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def signal_handler(sig):
            logger.info(f"Received signal {sig.name}, shutting down")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

        try:
            # Initialize services
            self.stdout.write('Initializing services...')
            
            # Start gRPC service
            grpc_connected = await grpc_service.initialize(peer_id)
            if grpc_connected:
                self.stdout.write(self.style.SUCCESS('✓ gRPC service connected'))
            else:
                self.stdout.write(self.style.WARNING('⚠ gRPC service offline (continuing in standalone mode)'))

            # Start stream service
            await stream_service.start()
            self.stdout.write(self.style.SUCCESS('✓ Stream service started'))

            # Start media scanner
            total, new, deleted = await scanner_service.scan_directories(media_dirs, settings.MEDIA_EXTENSIONS)
            self.stdout.write(self.style.SUCCESS(f'✓ Initial scan completed: {total} files ({new} new, {deleted} deleted)'))

            # Announce new media to gRPC if connected
            if grpc_connected and new > 0:
                # Get newly scanned media
                from ...infrastructure.repositories import get_media_repository
                media_repo = get_media_repository()
                new_media = [m for m in media_repo.get_all() if not m.catalog_id]
                
                if new_media:
                    success = await grpc_service.announce_new_media(new_media)
                    if success:
                        self.stdout.write(self.style.SUCCESS(f'✓ Announced {len(new_media)} new media files'))

            self.stdout.write(self.style.SUCCESS('🚀 Peer service is running'))
            self.stdout.write('Press Ctrl+C to stop')

            # Start periodic scanning
            scan_task = asyncio.create_task(self._periodic_scan(scanner_service, media_dirs, scan_interval, grpc_service))

            # Wait for stop signal
            await stop_event.wait()

            # Cleanup
            self.stdout.write('Stopping services...')
            scan_task.cancel()
            
            await stream_service.stop()
            await grpc_service.shutdown()
            
            self.stdout.write(self.style.SUCCESS('✓ Peer service stopped'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error in peer service: {e}'))
            logger.exception("Peer service error")
            raise

    async def _periodic_scan(self, scanner_service, media_dirs: list, interval: int, grpc_service):
        """Periodically scan for media changes."""
        while True:
            try:
                await asyncio.sleep(interval)
                
                logger.info("Starting periodic media scan")
                total, new, deleted = await scanner_service.scan_directories(media_dirs, settings.MEDIA_EXTENSIONS)
                
                if new > 0 or deleted > 0:
                    logger.info(f"Scan completed: {total} files ({new} new, {deleted} deleted)")
                    
                    # Announce changes to gRPC if connected
                    if grpc_service.is_connected() and new > 0:
                        from ...infrastructure.repositories import get_media_repository
                        media_repo = get_media_repository()
                        new_media = [m for m in media_repo.get_all() if not m.catalog_id]
                        
                        if new_media:
                            await grpc_service.announce_new_media(new_media)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic scan: {e}")
