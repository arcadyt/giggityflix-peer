import asyncio
import hashlib
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType
from giggityflix_peer.services.config_service import config_service

logger = logging.getLogger(__name__)


def get_media_type(file_path: Path) -> MediaType:
    """Determine the media type based on file extension."""
    ext = file_path.suffix.lower()

    # Video extensions
    if ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg']:
        return MediaType.VIDEO

    # Audio extensions
    if ext in ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma']:
        return MediaType.AUDIO

    # Image extensions
    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg']:
        return MediaType.IMAGE

    return MediaType.UNKNOWN


async def calculate_file_hash(file_path: Path, algorithm: str = 'md5') -> str:
    """Calculate the hash of a file."""
    hash_obj = hashlib.new(algorithm)
    chunk_size = 8192  # 8KB chunks

    # Open the file in binary mode
    with open(file_path, 'rb') as f:
        # Process the file in chunks to avoid loading large files into memory
        for chunk in iter(lambda: f.read(chunk_size), b''):
            hash_obj.update(chunk)

    return hash_obj.hexdigest()


class MediaScanner:
    """Scans directories for media files and updates the database."""

    def __init__(self, db_service):
        """Initialize the media scanner."""
        self.db_service = db_service
        self._media_dirs = []
        self._include_extensions = []
        self._exclude_dirs = []
        self._extract_metadata = True
        self._scan_interval = 60 * 60  # Default to 1 hour in seconds
        
        self._observer = None
        self._scanning = False
        self._stop_event = asyncio.Event()

    async def reload_config(self) -> None:
        """Reload scanner configuration from the config service."""
        # Get configuration from config service
        self._media_dirs = [Path(p) for p in await config_service.get("media_dirs", [])]
        self._include_extensions = await config_service.get("include_extensions", [".mp4", ".mkv", ".avi", ".mov"])
        self._exclude_dirs = [Path(p) for p in await config_service.get("exclude_dirs", [])]
        self._extract_metadata = await config_service.get("extract_metadata", True)
        
        # Convert scan interval from minutes to seconds
        scan_interval_minutes = await config_service.get("scan_interval_minutes", 60)
        self._scan_interval = scan_interval_minutes * 60
        
        logger.info(f"Scanner configuration reloaded: {len(self._media_dirs)} directories, "
                    f"{len(self._include_extensions)} extensions, {self._scan_interval/60} minutes interval")
        
        # If observer is already running, restart it with new config
        if self._observer and self._observer.is_alive():
            await self._restart_observer()

    async def start(self) -> None:
        """Start the media scanner."""
        logger.info("Starting media scanner")
        
        # Reload configuration
        await self.reload_config()

        # Start the file system observer
        await self._start_observer()

        # Start the periodic scan task
        asyncio.create_task(self._periodic_scan())

    async def stop(self) -> None:
        """Stop the media scanner."""
        logger.info("Stopping media scanner")

        # Stop the observer
        if self._observer:
            self._observer.stop()
            self._observer = None

        # Stop the periodic scan
        self._stop_event.set()

        # Wait for any ongoing scan to complete
        while self._scanning:
            await asyncio.sleep(0.1)

    async def scan_now(self) -> None:
        """Trigger an immediate scan."""
        if self._scanning:
            logger.info("Scan already in progress")
            return

        # Reload config before scanning
        await self.reload_config()
        
        asyncio.create_task(self._scan_media_dirs())
        
    async def _restart_observer(self) -> None:
        """Restart file system observer with updated configuration."""
        # Stop current observer
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            
        # Start new observer
        await self._start_observer()

    async def _start_observer(self) -> None:
        """Start the file system observer for real-time updates."""

        class MediaEventHandler(FileSystemEventHandler):
            def __init__(self, scanner):
                self.scanner = scanner

            def on_created(self, event):
                if not event.is_directory and self._is_media_file(event.src_path):
                    logger.debug(f"File created: {event.src_path}")
                    asyncio.create_task(self.scanner._process_new_file(Path(event.src_path)))

            def on_deleted(self, event):
                if not event.is_directory and self._is_media_file(event.src_path):
                    logger.debug(f"File deleted: {event.src_path}")
                    asyncio.create_task(self.scanner._process_deleted_file(Path(event.src_path)))

            def on_modified(self, event):
                if not event.is_directory and self._is_media_file(event.src_path):
                    logger.debug(f"File modified: {event.src_path}")
                    asyncio.create_task(self.scanner._process_modified_file(Path(event.src_path)))

            def on_moved(self, event):
                if not event.is_directory:
                    src_is_media = self._is_media_file(event.src_path)
                    dest_is_media = self._is_media_file(event.dest_path)

                    if src_is_media and dest_is_media:
                        logger.debug(f"File moved: {event.src_path} -> {event.dest_path}")
                        asyncio.create_task(self.scanner._process_moved_file(
                            Path(event.src_path), Path(event.dest_path)))
                    elif src_is_media:
                        logger.debug(f"File moved out: {event.src_path}")
                        asyncio.create_task(self.scanner._process_deleted_file(Path(event.src_path)))
                    elif dest_is_media:
                        logger.debug(f"File moved in: {event.dest_path}")
                        asyncio.create_task(self.scanner._process_new_file(Path(event.dest_path)))

            def _is_media_file(self, path: str) -> bool:
                """Check if the file is a media file based on extension."""
                path_obj = Path(path)
                return any(path_obj.suffix.lower() == ext for ext in self.scanner._include_extensions)

        # Create and start the observer
        self._observer = Observer()
        event_handler = MediaEventHandler(self)

        # Add watchers for all media directories
        for media_dir in self._media_dirs:
            if media_dir.exists() and media_dir.is_dir():
                self._observer.schedule(event_handler, str(media_dir), recursive=True)
                logger.info(f"Watching directory: {media_dir}")

        self._observer.start()

    async def _periodic_scan(self) -> None:
        """Periodically scan media directories."""
        # Perform an initial scan
        await self._scan_media_dirs()

        while not self._stop_event.is_set():
            # Wait for the scan interval
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._scan_interval)
            except asyncio.TimeoutError:
                # Timeout occurred, reload config and perform the scan
                await self.reload_config()
                await self._scan_media_dirs()

    async def _scan_media_dirs(self) -> None:
        """Scan all media directories for files."""
        if self._scanning:
            logger.info("Scan already in progress")
            return

        self._scanning = True
        logger.info("Starting media directory scan")

        try:
            start_time = time.time()
            total_files = 0
            new_files = 0

            # Get existing files from the database
            existing_files = await self.db_service.get_all_media_files()
            existing_paths = {str(file.path): file for file in existing_files}

            # Track processed paths to detect deleted files
            processed_paths = set()

            # Scan each media directory
            for media_dir in self._media_dirs:
                if not media_dir.exists() or not media_dir.is_dir():
                    logger.warning(f"Media directory does not exist: {media_dir}")
                    continue

                logger.info(f"Scanning directory: {media_dir}")

                for root, dirs, files in os.walk(media_dir):
                    # Skip excluded directories
                    dirs[:] = [d for d in dirs if Path(os.path.join(root, d)) not in self._exclude_dirs]

                    for file in files:
                        file_path = Path(os.path.join(root, file))

                        # Check if the file has a supported extension
                        if not any(file_path.suffix.lower() == ext for ext in self._include_extensions):
                            continue

                        total_files += 1
                        str_path = str(file_path)
                        processed_paths.add(str_path)

                        if str_path in existing_paths:
                            # File already exists in the database
                            # Check if it needs to be updated
                            existing_file = existing_paths[str_path]

                            if await self._check_file_changed(file_path, existing_file):
                                await self._process_modified_file(file_path)
                        else:
                            # New file
                            await self._process_new_file(file_path)
                            new_files += 1

            # Check for deleted files
            deleted_files = 0
            for path in existing_paths:
                if path not in processed_paths:
                    await self._process_deleted_file(Path(path))
                    deleted_files += 1

            elapsed_time = time.time() - start_time
            logger.info(
                f"Scan completed in {elapsed_time:.2f} seconds. "
                f"Total files: {total_files}, New: {new_files}, Deleted: {deleted_files}"
            )

        except Exception as e:
            logger.error(f"Error during media scan: {e}", exc_info=True)
        finally:
            self._scanning = False

    async def _check_file_changed(self, file_path: Path, existing_file: MediaFile) -> bool:
        """Check if a file has changed since the last scan."""
        if not file_path.exists():
            return False

        # Check if the file size has changed
        try:
            stat = file_path.stat()
            if stat.st_size != existing_file.size_bytes:
                return True

            # Check if the modification time has changed
            mtime = datetime.fromtimestamp(stat.st_mtime)
            if existing_file.modified_at and mtime > existing_file.modified_at:
                return True
        except (OSError, IOError) as e:
            logger.error(f"Error checking file {file_path}: {e}")
            return False

        return False

    async def _process_new_file(self, file_path: Path) -> Optional[MediaFile]:
        """Process a newly discovered media file."""
        if not file_path.exists():
            return None

        try:
            # Get file details
            stat = file_path.stat()
            size_bytes = stat.st_size
            created_at = datetime.fromtimestamp(stat.st_ctime)
            modified_at = datetime.fromtimestamp(stat.st_mtime)

            # Generate a local unique ID
            luid = str(uuid.uuid4())

            # Determine the relative path for any of the media directories
            relative_path = None
            for media_dir in self._media_dirs:
                try:
                    relative = file_path.relative_to(media_dir)
                    relative_path = str(relative)
                    break
                except ValueError:
                    continue

            # Create the media file object
            media_file = MediaFile(
                luid=luid,
                path=file_path,
                relative_path=relative_path,
                size_bytes=size_bytes,
                media_type=get_media_type(file_path),
                created_at=created_at,
                modified_at=modified_at,
                status=MediaStatus.PENDING
            )

            # Calculate file hashes for a default algorithm (MD5)
            # Don't pre-calculate all hashes, only calculate when Edge requests them
            hashes = {}
            try:
                hashes['md5'] = await calculate_file_hash(file_path, 'md5')
            except Exception as e:
                logger.error(f"Error calculating MD5 hash for {file_path}: {e}")

            media_file.hashes = hashes

            # Extract metadata if enabled
            if self._extract_metadata and media_file.media_type == MediaType.VIDEO:
                # This would typically use a library like ffprobe to extract video metadata
                # For now, we'll leave this as a placeholder
                pass

            # Save the media file to the database
            await self.db_service.add_media_file(media_file)
            logger.info(f"Added new media file: {file_path}")

            return media_file

        except Exception as e:
            logger.error(f"Error processing new file {file_path}: {e}", exc_info=True)
            return None

    async def _process_deleted_file(self, file_path: Path) -> None:
        """Process a deleted media file."""
        try:
            # Check if the file exists in the database
            media_file = await self.db_service.get_media_file_by_path(str(file_path))
            if not media_file:
                return

            # Mark the file as deleted
            media_file.status = MediaStatus.DELETED
            await self.db_service.update_media_file(media_file)
            logger.info(f"Marked media file as deleted: {file_path}")

        except Exception as e:
            logger.error(f"Error processing deleted file {file_path}: {e}", exc_info=True)

    async def _process_modified_file(self, file_path: Path) -> None:
        """Process a modified media file."""
        if not file_path.exists():
            await self._process_deleted_file(file_path)
            return

        try:
            # Check if the file exists in the database
            media_file = await self.db_service.get_media_file_by_path(str(file_path))
            if not media_file:
                # File not found, process as new
                await self._process_new_file(file_path)
                return

            # Update file details
            stat = file_path.stat()
            media_file.size_bytes = stat.st_size
            media_file.modified_at = datetime.fromtimestamp(stat.st_mtime)

            # Update MD5 hash (don't calculate all hashes, only when requested)
            try:
                media_file.hashes['md5'] = await calculate_file_hash(file_path, 'md5')
            except Exception as e:
                logger.error(f"Error calculating MD5 hash for {file_path}: {e}")

            # Extract metadata if enabled
            if self._extract_metadata and media_file.media_type == MediaType.VIDEO:
                # This would typically use a library like ffprobe to extract video metadata
                # For now, we'll leave this as a placeholder
                pass

            # Update the media file in the database
            await self.db_service.update_media_file(media_file)
            logger.info(f"Updated modified media file: {file_path}")

        except Exception as e:
            logger.error(f"Error processing modified file {file_path}: {e}", exc_info=True)

    async def _process_moved_file(self, old_path: Path, new_path: Path) -> None:
        """Process a moved media file."""
        if not new_path.exists():
            await self._process_deleted_file(old_path)
            return

        try:
            # Check if the old file exists in the database
            media_file = await self.db_service.get_media_file_by_path(str(old_path))
            if not media_file:
                # Old file not found, process as new
                await self._process_new_file(new_path)
                return

            # Update the path
            media_file.path = new_path

            # Update the relative path
            relative_path = None
            for media_dir in self._media_dirs:
                try:
                    relative = new_path.relative_to(media_dir)
                    relative_path = str(relative)
                    break
                except ValueError:
                    continue

            media_file.relative_path = relative_path

            # Update the media file in the database
            await self.db_service.update_media_file(media_file)
            logger.info(f"Updated moved media file: {old_path} -> {new_path}")

        except Exception as e:
            logger.error(f"Error processing moved file {old_path} -> {new_path}: {e}", exc_info=True)
