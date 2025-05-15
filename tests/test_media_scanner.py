import asyncio
import tempfile
from pathlib import Path
from unittest import mock

import pytest
from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileModifiedEvent, FileMovedEvent

from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType
from giggityflix_peer.scanner.media_scanner import MediaScanner, get_media_type


class TestMediaScanner:
    """Test suite for the MediaScanner class."""

    @pytest.fixture
    def mock_db_service(self):
        """Mock database service."""
        db_service = mock.AsyncMock()
        db_service.get_all_media_files.return_value = []
        return db_service

    @pytest.fixture
    def test_media_dir(self):
        """Create a temporary directory for media files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def scanner(self, mock_db_service, test_media_dir):
        """Create a MediaScanner instance with mocks."""
        with mock.patch("src.scanner.media_scanner.config") as mock_config:
            # Configure scanner
            mock_config.scanner.media_dirs = [str(test_media_dir)]
            mock_config.scanner.include_extensions = [".mp4", ".mkv", ".mp3"]
            mock_config.scanner.exclude_dirs = []
            mock_config.scanner.hash_algorithms = ["md5"]
            mock_config.scanner.extract_metadata = False
            mock_config.scanner.scan_interval_minutes = 1
            
            # Create scanner with mocked db_service
            scanner = MediaScanner(mock_db_service)
            
            yield scanner
            
            # Clean up
            loop = asyncio.get_event_loop()
            if scanner._observer:
                scanner._observer.stop()
                scanner._observer = None

    def test_get_media_type(self):
        """Test the get_media_type function."""
        # Test video extensions
        assert get_media_type(Path("test.mp4")) == MediaType.VIDEO
        assert get_media_type(Path("test.mkv")) == MediaType.VIDEO
        assert get_media_type(Path("test.avi")) == MediaType.VIDEO
        
        # Test audio extensions
        assert get_media_type(Path("test.mp3")) == MediaType.AUDIO
        assert get_media_type(Path("test.wav")) == MediaType.AUDIO
        assert get_media_type(Path("test.flac")) == MediaType.AUDIO
        
        # Test image extensions
        assert get_media_type(Path("test.jpg")) == MediaType.IMAGE
        assert get_media_type(Path("test.png")) == MediaType.IMAGE
        assert get_media_type(Path("test.gif")) == MediaType.IMAGE
        
        # Test unknown extension
        assert get_media_type(Path("test.txt")) == MediaType.UNKNOWN

    @pytest.mark.asyncio
    async def test_scan_empty_directory(self, scanner, test_media_dir):
        """Test scanning an empty directory."""
        # Start the scanner
        await scanner.start()
        
        try:
            # Trigger a scan
            await scanner.scan_now()
            
            # Check that the database service was called
            scanner.db_service.get_all_media_files.assert_called_once()
            
            # There should be no calls to add_media_file
            scanner.db_service.add_media_file.assert_not_called()
        finally:
            # Stop the scanner
            await scanner.stop()

    @pytest.mark.asyncio
    async def test_scan_with_media_files(self, scanner, test_media_dir):
        """Test scanning a directory with media files."""
        # Create some test media files
        test_files = [
            test_media_dir / "test1.mp4",
            test_media_dir / "test2.mkv",
            test_media_dir / "test3.mp3",
            test_media_dir / "ignored.txt"  # Should be ignored
        ]
        
        for file_path in test_files:
            with open(file_path, "wb") as f:
                f.write(b"test data")
        
        # Configure mock to return empty list (no existing files)
        scanner.db_service.get_all_media_files.return_value = []
        
        # Mock the calculate_file_hash function to avoid actual hashing
        with mock.patch("src.scanner.media_scanner.calculate_file_hash", 
                        return_value="mock_hash"):
            # Start the scanner
            await scanner.start()
            
            try:
                # Trigger a scan
                await scanner.scan_now()
                
                # Check that the database service was called
                scanner.db_service.get_all_media_files.assert_called_once()
                
                # Three media files should be processed, text file ignored
                assert scanner.db_service.add_media_file.call_count == 3
                
                # Check the arguments of each call
                call_args_list = scanner.db_service.add_media_file.call_args_list
                media_files = [args[0][0] for args in call_args_list]
                
                assert len(media_files) == 3
                
                # Check each media file
                for media_file in media_files:
                    assert isinstance(media_file, MediaFile)
                    assert media_file.status == MediaStatus.PENDING
                    assert media_file.hashes == {"md5": "mock_hash"}
                    
                    # Check file path
                    file_path = str(media_file.path)
                    assert any(str(test_file) == file_path for test_file in test_files[:3])
                    
                    # Check media type
                    if file_path.endswith(".mp4") or file_path.endswith(".mkv"):
                        assert media_file.media_type == MediaType.VIDEO
                    elif file_path.endswith(".mp3"):
                        assert media_file.media_type == MediaType.AUDIO
            finally:
                # Stop the scanner
                await scanner.stop()

    @pytest.mark.asyncio
    async def test_scan_with_existing_files(self, scanner, test_media_dir):
        """Test scanning with existing files in the database."""
        # Create a test media file
        test_file = test_media_dir / "test1.mp4"
        with open(test_file, "wb") as f:
            f.write(b"test data")
        
        # Create an existing media file record
        existing_file = MediaFile(
            luid="existing-luid",
            path=test_file,
            size_bytes=9,  # Different from actual size to trigger update
            media_type=MediaType.VIDEO,
            status=MediaStatus.READY,
            hashes={"md5": "old_hash"}
        )
        
        # Configure mock to return the existing file
        scanner.db_service.get_all_media_files.return_value = [existing_file]
        scanner.db_service.get_media_file_by_path.return_value = existing_file
        
        # Mock the check_file_changed and calculate_file_hash functions
        with mock.patch("src.scanner.media_scanner.MediaScanner._check_file_changed", 
                        return_value=True), \
             mock.patch("src.scanner.media_scanner.calculate_file_hash", 
                        return_value="new_hash"):
            
            # Start the scanner
            await scanner.start()
            
            try:
                # Trigger a scan
                await scanner.scan_now()
                
                # File should be updated, not added
                scanner.db_service.add_media_file.assert_not_called()
                scanner.db_service.update_media_file.assert_called_once()
                
                # Check the updated file
                updated_file = scanner.db_service.update_media_file.call_args[0][0]
                assert updated_file.luid == "existing-luid"
                assert updated_file.hashes == {"md5": "new_hash"}
            finally:
                # Stop the scanner
                await scanner.stop()

    @pytest.mark.asyncio
    async def test_file_event_handlers(self, scanner, test_media_dir):
        """Test file event handlers (created, modified, deleted, moved)."""
        # Mock the process methods
        with mock.patch.object(MediaScanner, "_process_new_file") as mock_new, \
             mock.patch.object(MediaScanner, "_process_modified_file") as mock_modified, \
             mock.patch.object(MediaScanner, "_process_deleted_file") as mock_deleted, \
             mock.patch.object(MediaScanner, "_process_moved_file") as mock_moved:
            
            # Create event handler from the scanner's _start_observer method
            await scanner.start()
            
            # Manually create and call event handlers
            # File created event
            event = FileCreatedEvent(str(test_media_dir / "new.mp4"))
            scanner._observer.dispatch_event(event)
            await asyncio.sleep(0.1)  # Give time for the async handler to run
            mock_new.assert_called_once_with(Path(event.src_path))
            
            # File modified event
            event = FileModifiedEvent(str(test_media_dir / "modified.mp4"))
            scanner._observer.dispatch_event(event)
            await asyncio.sleep(0.1)
            mock_modified.assert_called_once_with(Path(event.src_path))
            
            # File deleted event
            event = FileDeletedEvent(str(test_media_dir / "deleted.mp4"))
            scanner._observer.dispatch_event(event)
            await asyncio.sleep(0.1)
            mock_deleted.assert_called_once_with(Path(event.src_path))
            
            # File moved event
            event = FileMovedEvent(
                str(test_media_dir / "old.mp4"),
                str(test_media_dir / "new_location.mp4")
            )
            scanner._observer.dispatch_event(event)
            await asyncio.sleep(0.1)
            mock_moved.assert_called_once_with(
                Path(event.src_path),
                Path(event.dest_path)
            )
            
            # Test ignored file (text file)
            mock_new.reset_mock()
            event = FileCreatedEvent(str(test_media_dir / "ignored.txt"))
            scanner._observer.dispatch_event(event)
            await asyncio.sleep(0.1)
            mock_new.assert_not_called()
            
            await scanner.stop()


@pytest.mark.asyncio
async def test_calculate_file_hash():
    """Test the calculate_file_hash function."""
    from giggityflix_peer import calculate_file_hash
    
    # Create a temporary file with known content
    with tempfile.NamedTemporaryFile() as tmp_file:
        tmp_file.write(b"test data")
        tmp_file.flush()
        
        # Calculate MD5 hash
        md5_hash = await calculate_file_hash(Path(tmp_file.name), "md5")
        assert md5_hash == "eb733a00c0c9d336e65691a37ab54293"
        
        # Calculate SHA1 hash
        sha1_hash = await calculate_file_hash(Path(tmp_file.name), "sha1")
        assert sha1_hash == "7d4e3eec80026719639ed4dba68916eb41dfdde0"
