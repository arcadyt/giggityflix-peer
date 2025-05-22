"""Media scanner service for discovering and tracking media files."""
import asyncio
import hashlib
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from giggityflix_peer.core.resource_pool.decorators import io_bound
from giggityflix_peer.apps.configuration import services as config_service

from ..domain.models import Media, MediaStatus, MediaType
from ..infrastructure.repositories import get_media_repository

logger = logging.getLogger(__name__)


class MediaScanner:
    """Service for scanning directories for media files."""
    
    def __init__(self):
        """Initialize the scanner service."""
        self.media_repository = get_media_repository()
        self._scanning = False
        self._stop_event = asyncio.Event()

    def get_media_type(self, file_path: Path) -> MediaType:
        """Determine media type based on file extension."""
        ext = file_path.suffix.lower()
        
        # Video extensions
        if ext in ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg']:
            return MediaType.VIDEO
        
        # Audio extensions
        if ext in ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma']:
            return MediaType.AUDIO

        return MediaType.UNSUPPORTED

    @io_bound(param_name='file_path')
    async def calculate_file_hash(self, file_path: Path, algorithm: str) -> str:
        """Calculate hash for a file using specified algorithm."""
        hash_obj = hashlib.new(algorithm)
        chunk_size = 8192  # 8KB chunks
        
        # Run file IO in a thread pool
        def read_and_hash():
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(chunk_size), b''):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, read_and_hash)
    
    async def scan_directories(self, directories: List[str], extensions: List[str]) -> Tuple[int, int, int]:
        """
        Scan directories for media files.
        
        Args:
            directories: List of directory paths to scan
            extensions: List of file extensions to include
            
        Returns:
            Tuple of (total_files, new_files, deleted_files)
        """
        if self._scanning:
            logger.info("Scan already in progress")
            return 0, 0, 0
        
        self._scanning = True
        new_files = 0
        deleted_files = 0
        
        try:
            # Get existing files from the database
            existing_files = self.media_repository.get_all()
            existing_paths = {media.path: media for media in existing_files}
            
            # Track processed paths
            processed_paths = set()
            
            # Scan directories
            for directory in directories:
                dir_path = Path(directory)
                if not dir_path.exists() or not dir_path.is_dir():
                    logger.warning(f"Directory does not exist or is not a directory: {directory}")
                    continue
                
                logger.info(f"Scanning directory: {directory}")
                
                # Walk directory tree
                for root, _, files in os.walk(directory):
                    for file in files:
                        file_path = Path(os.path.join(root, file))
                        
                        # Check if file has a supported extension
                        if not any(file_path.suffix.lower() == ext for ext in extensions):
                            continue
                        
                        str_path = str(file_path)
                        processed_paths.add(str_path)
                        
                        if str_path in existing_paths:
                            # File already exists in database, check if it changed
                            if await self._check_file_changed(file_path, existing_paths[str_path]):
                                await self._process_changed_file(file_path, existing_paths[str_path])
                        else:
                            # New file
                            await self._process_new_file(file_path, directory)
                            new_files += 1
            
            # Check for deleted files
            for path, media in existing_paths.items():
                if path not in processed_paths and media.status != MediaStatus.DELETED:
                    media.status = MediaStatus.DELETED
                    self.media_repository.save(media)
                    deleted_files += 1
            
            return len(processed_paths), new_files, deleted_files
        
        finally:
            self._scanning = False
    
    async def _check_file_changed(self, file_path: Path, media: Media) -> bool:
        """Check if a file has changed since it was last scanned."""
        if not file_path.exists():
            return False
        
        try:
            stat = file_path.stat()
            
            # Check size
            if stat.st_size != media.size_bytes:
                return True
            
            # Check modification time
            mtime = datetime.fromtimestamp(stat.st_mtime)
            if media.modified_at and mtime > media.modified_at:
                return True
            
            return False
        
        except (OSError, IOError) as e:
            logger.error(f"Error checking file {file_path}: {e}")
            return False
    
    async def _process_new_file(self, file_path: Path, base_dir: str) -> Optional[Media]:
        """Process a newly discovered file."""
        if not file_path.exists():
            return None
        
        try:
            # Get file details
            stat = file_path.stat()
            size_bytes = stat.st_size
            created_at = datetime.fromtimestamp(stat.st_ctime)
            modified_at = datetime.fromtimestamp(stat.st_mtime)
            
            # Generate LUID
            luid = str(uuid.uuid4())
            
            # Calculate relative path
            try:
                relative = file_path.relative_to(Path(base_dir))
                relative_path = str(relative)
            except ValueError:
                relative_path = None
            
            # Create Media object
            media = Media(
                luid=luid,
                path=str(file_path),
                relative_path=relative_path,
                size_bytes=size_bytes,
                media_type=self.get_media_type(file_path),
                status=MediaStatus.PENDING,
                created_at=created_at,
                modified_at=modified_at
            )
            
            # Calculate MD5 hash
            try:
                md5_hash = await self.calculate_file_hash(file_path, 'md5')
                media.hashes['md5'] = md5_hash
            except Exception as e:
                logger.error(f"Failed to calculate MD5 hash for {file_path}: {e}")
            
            # Save to repository
            self.media_repository.save(media)
            logger.info(f"Added new media file: {file_path}")
            
            return media
        
        except Exception as e:
            logger.error(f"Error processing new file {file_path}: {e}")
            return None
    
    async def _process_changed_file(self, file_path: Path, media: Media) -> None:
        """Process a changed file."""
        if not file_path.exists():
            media.status = MediaStatus.DELETED
            self.media_repository.save(media)
            return
        
        try:
            # Update file details
            stat = file_path.stat()
            media.size_bytes = stat.st_size
            media.modified_at = datetime.fromtimestamp(stat.st_mtime)
            
            # Recalculate MD5 hash
            try:
                md5_hash = await self.calculate_file_hash(file_path, 'md5')
                media.hashes['md5'] = md5_hash
            except Exception as e:
                logger.error(f"Failed to calculate MD5 hash for {file_path}: {e}")
            
            # Save updated media
            self.media_repository.save(media)
            logger.info(f"Updated changed media file: {file_path}")
        
        except Exception as e:
            logger.error(f"Error processing changed file {file_path}: {e}")


# Singleton instance
_media_scanner = None


def get_media_scanner() -> MediaScanner:
    """Get or create a MediaScanner instance."""
    global _media_scanner
    if _media_scanner is None:
        _media_scanner = MediaScanner()
    return _media_scanner
