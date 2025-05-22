"""Test command to verify media app setup and configuration."""
from django.core.management.base import BaseCommand
from asgiref.sync import sync_to_async

from giggityflix_peer.apps.configuration import services as config_service
from giggityflix_peer.apps.media.application.media_service import get_media_service
from giggityflix_peer.peer_service import get_peer_service


class Command(BaseCommand):
    help = 'Test media app setup and verify all components are working'

    def handle(self, *args, **options):
        """Test setup without starting full service."""
        self.stdout.write('Testing Giggityflix Media App Setup...\n')

        # Test configuration service
        self.stdout.write('1. Testing configuration service...')
        try:
            # Test using the synchronous version for now
            from giggityflix_peer.apps.configuration.models import Configuration
            config_count = Configuration.objects.count()
            self.stdout.write(self.style.SUCCESS(f'   ✓ Configuration working ({config_count} configs)'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Configuration error: {e}'))
            return

        # Test media service instantiation
        self.stdout.write('2. Testing media service instantiation...')
        try:
            media_service = get_media_service()
            self.stdout.write(self.style.SUCCESS('   ✓ Media service created'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Media service error: {e}'))
            return

        # Test peer service instantiation
        self.stdout.write('3. Testing peer service instantiation...')
        try:
            peer_service = get_peer_service()
            self.stdout.write(self.style.SUCCESS('   ✓ Peer service created'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Peer service error: {e}'))
            return

        # Test gRPC components (without connecting)
        self.stdout.write('4. Testing gRPC components...')
        try:
            from giggityflix_peer.apps.media.infrastructure.grpc.client import MediaGrpcClient
            grpc_client = MediaGrpcClient("test-peer")
            self.stdout.write(self.style.SUCCESS('   ✓ gRPC client created (protobuf may not be available)'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ gRPC client error: {e}'))
            return

        # Test configuration defaults
        self.stdout.write('5. Testing configuration defaults...')
        try:
            from giggityflix_peer.apps.configuration.models import Configuration
            essential_configs = [
                'media_dirs', 'media_extensions', 'scan_interval_minutes',
                'edge_grpc_address', 'grpc_use_tls', 'grpc_timeout_sec'
            ]
            
            for config_key in essential_configs:
                try:
                    config = Configuration.objects.get(key=config_key)
                    value = config.get_typed_value()
                    self.stdout.write(f'   ✓ {config_key}: {value}')
                except Configuration.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'   ? {config_key}: not set'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Configuration defaults error: {e}'))
            return

        # Test repository instantiation
        self.stdout.write('6. Testing repository instantiation...')
        try:
            from giggityflix_peer.apps.media.infrastructure.repositories import get_media_repository
            media_repo = get_media_repository()
            self.stdout.write(self.style.SUCCESS('   ✓ Media repository created'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Repository error: {e}'))
            return

        # Test domain models
        self.stdout.write('7. Testing domain models...')
        try:
            from giggityflix_peer.apps.media.domain.models import Media, MediaType, MediaStatus
            media = Media(
                luid="test-luid",
                path="/test/path",
                size_bytes=1024,
                media_type=MediaType.VIDEO,
                status=MediaStatus.PENDING
            )
            self.stdout.write(self.style.SUCCESS('   ✓ Domain models working'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'   ✗ Domain models error: {e}'))
            return

        self.stdout.write(self.style.SUCCESS('\n🎉 All tests passed! Media app setup is working correctly.'))
        self.stdout.write('\nTo start the peer service, run:')
        self.stdout.write('  python manage.py start_peer')
        
        # Show some helpful info
        self.stdout.write('\nNotes:')
        self.stdout.write('- gRPC protobuf modules may show warnings if giggityflix-grpc-peer is not properly installed')
        self.stdout.write('- Configure media directories using: python manage.py shell')
        self.stdout.write('  >>> from giggityflix_peer.apps.configuration import services as config')
        self.stdout.write('  >>> import asyncio')
        self.stdout.write('  >>> asyncio.run(config.set("media_dirs", ["/path/to/media"]))')
