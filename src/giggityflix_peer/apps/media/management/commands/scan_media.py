"""Management command to scan media directories."""
import asyncio
import time
from typing import Any, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ....application.scanner_service import get_media_scanner


class Command(BaseCommand):
    help = 'Scan media directories for media files'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--directories',
            nargs='+',
            help='Directories to scan, space-separated'
        )
        parser.add_argument(
            '--extensions',
            nargs='+',
            help='File extensions to include, space-separated'
        )
    
    def handle(self, *args: Any, **options: Any) -> Optional[str]:
        start_time = time.time()
        
        # Get directories from args or settings
        directories = options.get('directories')
        if not directories:
            directories = getattr(settings, 'MEDIA_DIRECTORIES', [])
            if not directories:
                raise CommandError(
                    'No directories specified. Either provide --directories '
                    'or set MEDIA_DIRECTORIES in settings.'
                )
        
        # Get extensions from args or settings
        extensions = options.get('extensions')
        if not extensions:
            extensions = getattr(settings, 'MEDIA_EXTENSIONS', [
                '.mp4', '.mkv', '.avi', '.mov', '.mp3', '.flac', '.jpg', '.png'
            ])
        
        # Get scanner
        scanner = get_media_scanner()
        
        # Run in event loop
        loop = asyncio.get_event_loop()
        total, new, deleted = loop.run_until_complete(
            scanner.scan_directories(directories, extensions)
        )
        
        elapsed_time = time.time() - start_time
        
        self.stdout.write(self.style.SUCCESS(
            f'Scan completed in {elapsed_time:.2f} seconds. '
            f'Found {total} files ({new} new, {deleted} deleted).'
        ))
