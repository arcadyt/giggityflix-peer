"""Django management command to start the peer service."""
import asyncio
import logging
import signal
import uuid
from typing import Optional

from django.core.management.base import BaseCommand
from giggityflix_peer.apps.configuration import services as config_service
from ...application.media_service import get_media_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Start the peer service with gRPC, media scanning, and streaming capabilities'

    def add_arguments(self, parser):
        parser.add_argument(
            '--peer-id',
            type=str,
            help='Unique identifier for this peer (auto-generated if not provided)'
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Get or generate peer ID
            peer_id = options.get('peer_id')
            if not peer_id:
                peer_id = asyncio.run(config_service.get('peer_id', ''))
                if not peer_id:
                    peer_id = str(uuid.uuid4())
                    asyncio.run(config_service.set('peer_id', peer_id))

            self.stdout.write(f'Starting peer service with ID: {peer_id}')

            # Run the async peer service
            asyncio.run(self._run_peer_service(peer_id))

        except KeyboardInterrupt:
            self.stdout.write('\nShutting down...')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error running peer service: {e}'))
            logger.exception("Peer service error")

    async def _run_peer_service(self, peer_id: str):
        """Run the peer service with all components."""
        media_service = get_media_service()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def signal_handler(sig):
            logger.info(f"Received signal {sig.name}, shutting down")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

        try:
            # Initialize media service
            self.stdout.write('Initializing media service...')
            success = await media_service.initialize(peer_id)
            
            if success:
                self.stdout.write(self.style.SUCCESS('✓ Media service initialized'))
            else:
                self.stdout.write(self.style.ERROR('✗ Media service initialization failed'))
                return

            # Perform initial scan
            self.stdout.write('Performing initial media scan...')
            scan_result = await media_service.scan_media_directories()
            self.stdout.write(self.style.SUCCESS(
                f'✓ Scan completed: {scan_result["total"]} files '
                f'({scan_result["new"]} new, {scan_result["deleted"]} deleted)'
            ))

            self.stdout.write(self.style.SUCCESS('🚀 Peer service is running'))
            self.stdout.write('Press Ctrl+C to stop')

            # Start periodic scanning
            scan_interval = await config_service.get('scan_interval_minutes', 60)
            scan_task = asyncio.create_task(
                self._periodic_scan(media_service, scan_interval * 60)
            )

            # Wait for stop signal
            await stop_event.wait()

            # Cleanup
            self.stdout.write('Stopping services...')
            scan_task.cancel()
            await media_service.shutdown()
            
            self.stdout.write(self.style.SUCCESS('✓ Peer service stopped'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error in peer service: {e}'))
            logger.exception("Peer service error")
            raise

    async def _periodic_scan(self, media_service, interval_seconds: int):
        """Periodically scan for media changes."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                
                logger.info("Starting periodic media scan")
                scan_result = await media_service.scan_media_directories()
                
                if scan_result['new'] > 0 or scan_result['deleted'] > 0:
                    logger.info(f"Scan completed: {scan_result}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic scan: {e}")
