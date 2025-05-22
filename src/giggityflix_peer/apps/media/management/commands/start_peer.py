"""Django management command to start the peer service."""
import asyncio
import logging
import signal
from typing import Optional

from django.core.management.base import BaseCommand
from giggityflix_peer.peer_service import get_peer_service
from giggityflix_peer.apps.configuration import services as config_service

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
            '--scan-interval',
            type=int,
            help='Media scan interval in minutes (overrides configuration)'
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        try:
            # Set peer ID if provided
            peer_id = options.get('peer_id')
            if peer_id:
                asyncio.run(config_service.set('peer_id', peer_id))

            # Set scan interval if provided
            scan_interval = options.get('scan_interval')
            if scan_interval:
                asyncio.run(config_service.set('scan_interval_minutes', scan_interval))

            self.stdout.write('Starting Giggityflix Peer Service...')

            # Run the async peer service
            asyncio.run(self._run_peer_service())

        except KeyboardInterrupt:
            self.stdout.write('\nShutting down...')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error running peer service: {e}'))
            logger.exception("Peer service error")

    async def _run_peer_service(self):
        """Run the peer service with all components."""
        peer_service = get_peer_service()

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def signal_handler(sig):
            logger.info(f"Received signal {sig.name}, shutting down")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))

        try:
            # Initialize peer service
            self.stdout.write('Initializing peer service...')
            success = await peer_service.initialize()
            
            if not success:
                self.stdout.write(self.style.ERROR('✗ Peer service initialization failed'))
                return

            # Start peer service
            self.stdout.write('Starting peer service...')
            started = await peer_service.start()
            
            if not started:
                self.stdout.write(self.style.ERROR('✗ Peer service start failed'))
                return

            self.stdout.write(self.style.SUCCESS('🚀 Peer service is running'))
            
            # Show connection status
            if peer_service.is_grpc_connected():
                self.stdout.write(self.style.SUCCESS('✓ Connected to Edge Service'))
            else:
                self.stdout.write(self.style.WARNING('⚠ Running in standalone mode (no Edge connection)'))

            self.stdout.write('Press Ctrl+C to stop')

            # Start periodic scanning
            scan_interval = await config_service.get('scan_interval_minutes', 60)
            if scan_interval > 0:
                scan_task = asyncio.create_task(
                    self._periodic_scan(peer_service, scan_interval * 60)
                )
            else:
                scan_task = None

            # Wait for stop signal
            await stop_event.wait()

            # Cleanup
            self.stdout.write('Stopping services...')
            if scan_task:
                scan_task.cancel()
            
            await peer_service.stop()
            
            self.stdout.write(self.style.SUCCESS('✓ Peer service stopped'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error in peer service: {e}'))
            logger.exception("Peer service error")
            raise

    async def _periodic_scan(self, peer_service, interval_seconds: int):
        """Periodically scan for media changes."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                
                logger.info("Starting periodic media scan")
                scan_result = await peer_service.trigger_media_scan()
                
                if scan_result['new'] > 0 or scan_result['deleted'] > 0:
                    logger.info(f"Scan completed: {scan_result}")
                    self.stdout.write(f"Scan: {scan_result['total']} total, "
                                     f"{scan_result['new']} new, {scan_result['deleted']} deleted")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic scan: {e}")
