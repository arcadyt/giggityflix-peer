import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from giggityflix_peer.scanner.media_scanner_updated import MediaScanner, calculate_file_hash

from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType


class TestMediaScannerUpdated:
    """Tests for the updated MediaScanner."""

    @pytest.fixture
    def mock_db_service(self):
        """Create a mock database service."""
        mock = MagicMock()
        mock.get_all_media_files = AsyncMock(return_value=[])
        mock.get_media_file = AsyncMock(return_value=None)
        mock.get_media_file_by_path = AsyncMock(return_value=None)
        mock.add_media_file = AsyncMock()
        mock.update_media_file = AsyncMock()
        return mock

    @pytest.fixture
    def mock_config_service(self):
        """Create a mock config service."""
        mock = MagicMock()
        mock.get = AsyncMock()

        # Set up default return values
        mock.get.side_effect = lambda key, default=None: {
            "media_dirs": ["/test/media"],
            "include_extensions": [".mp4", ".mkv"],
            "exclude_dirs": ["/test/media/exclude"],
            "extract_metadata": True,
            "scan_interval_minutes": 60
        }.get(key, default)

        return mock

    @pytest.fixture
    def scanner(self, mock_db_service):
        """Create a scanner with mock services."""
        return MediaScanner(mock_db_service)

    @pytest.mark.asyncio
    async def test_reload_config(self, scanner, mock_config_service):
        """Test reloading configuration from config service."""
        # Patch the config_service module reference
        with patch("giggityflix_peer.scanner.media_scanner_updated.config_service", mock_config_service):
            # Call the method
            await scanner.reload_config()

            # Check that config service was called correctly
            mock_config_service.get.assert_any_call("media_dirs", [])
            mock_config_service.get.assert_any_call("include_extensions", [".mp4", ".mkv", ".avi", ".mov"])
            mock_config_service.get.assert_any_call("exclude_dirs", [])
            mock_config_service.get.assert_any_call("extract_metadata", True)
            mock_config_service.get.assert_any_call("scan_interval_minutes", 60)

            # Check that the values were set correctly
            assert scanner._media_dirs == [Path("/test/media")]
            assert scanner._include_extensions == [".mp4", ".mkv"]
            assert scanner._exclude_dirs == [Path("/test/media/exclude")]
            assert scanner._extract_metadata is True
            assert scanner._scan_interval == 60 * 60  # Minutes to seconds

    @pytest.mark.asyncio
    async def test_start_calls_reload_config(self, scanner):
        """Test that start calls reload_config."""
        # Mock the reload_config and _start_observer methods
        scanner.reload_config = AsyncMock()
        scanner._start_observer = AsyncMock()
        scanner._periodic_scan = AsyncMock()

        # Patch asyncio.create_task
        with patch("asyncio.create_task") as mock_create_task:
            # Call start
            await scanner.start()

            # Check that reload_config was called
            scanner.reload_config.assert_called_once()

            # Check that _start_observer was called
            scanner._start_observer.assert_called_once()

            # Check that create_task was called
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_now_calls_reload_config(self, scanner):
        """Test that scan_now calls reload_config."""
        # Mock the reload_config method
        scanner.reload_config = AsyncMock()
        scanner._scan_media_dirs = AsyncMock()

        # Patch asyncio.create_task
        with patch("asyncio.create_task") as mock_create_task:
            # Set scanner not scanning
            scanner._scanning = False

            # Call scan_now
            await scanner.scan_now()

            # Check that reload_config was called
            scanner.reload_config.assert_called_once()

            # Check that create_task was called
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_periodic_scan_calls_reload_config(self, scanner):
        """Test that _periodic_scan calls reload_config."""
        # Mock the reload_config and _scan_media_dirs methods
        scanner.reload_config = AsyncMock()
        scanner._scan_media_dirs = AsyncMock()

        # Set up a mock timeout to trigger the scan
        with patch("asyncio.wait_for") as mock_wait_for:
            # Make wait_for raise a TimeoutError to trigger the scan
            mock_wait_for.side_effect = asyncio.TimeoutError()

            # Set up to exit after one loop
            scanner._stop_event = MagicMock()
            scanner._stop_event.is_set.side_effect = [False, True]  # First check False, then True to exit loop

            # Call _periodic_scan
            await scanner._periodic_scan()

            # Check that reload_config was called
            scanner.reload_config.assert_called_once()

            # Check that _scan_media_dirs was called
            scanner._scan_media_dirs.assert_has_calls([call(), call()])  # Once for initial scan, once after timeout

    @pytest.mark.asyncio
    async def test_process_new_file_calculates_md5(self, scanner, mock_db_service):
        """Test that _process_new_file calculates MD5 hash only."""
        # Create a mock file
        file_path = Path("/test/media/test.mp4")

        # Mock the file_path.exists method
        with patch.object(file_path, "exists", return_value=True), \
                patch.object(file_path, "stat") as mock_stat, \
                patch("giggityflix_peer.scanner.media_scanner_updated.calculate_file_hash",
                      AsyncMock(return_value="test_hash")) as mock_calculate_hash:
            # Set up the stat return value
            mock_stat_result = MagicMock()
            mock_stat_result.st_size = 1000
            mock_stat_result.st_ctime = datetime.now().timestamp()
            mock_stat_result.st_mtime = datetime.now().timestamp()
            mock_stat.return_value = mock_stat_result

            # Set up media dirs for relative path calculation
            scanner._media_dirs = [Path("/test/media")]

            # Call the method
            await scanner._process_new_file(file_path)

            # Check that calculate_file_hash was called only for MD5
            mock_calculate_hash.assert_called_once_with(file_path, 'md5')

            # Check that add_media_file was called with a MediaFile containing just MD5 hash
            assert mock_db_service.add_media_file.call_count == 1
            media_file = mock_db_service.add_media_file.call_args[0][0]
            assert 'md5' in media_file.hashes
            assert len(media_file.hashes) == 1

    @pytest.mark.asyncio
    async def test_process_modified_file_updates_md5(self, scanner, mock_db_service):
        """Test that _process_modified_file updates MD5 hash only."""
        # Create a mock file
        file_path = Path("/test/media/test.mp4")

        # Create a mock media file
        media_file = MediaFile(
            luid="test_luid",
            path=file_path,
            relative_path="test.mp4",
            size_bytes=1000,
            media_type=MediaType.VIDEO,
            status=MediaStatus.READY,
            hashes={"md5": "old_hash"}
        )

        # Set up the mock to return the media file
        mock_db_service.get_media_file_by_path.return_value = media_file

        # Mock the file_path.exists method
        with patch.object(file_path, "exists", return_value=True), \
                patch.object(file_path, "stat") as mock_stat, \
                patch("giggityflix_peer.scanner.media_scanner_updated.calculate_file_hash",
                      AsyncMock(return_value="new_hash")) as mock_calculate_hash:
            # Set up the stat return value
            mock_stat_result = MagicMock()
            mock_stat_result.st_size = 1000
            mock_stat_result.st_mtime = datetime.now().timestamp()
            mock_stat.return_value = mock_stat_result

            # Call the method
            await scanner._process_modified_file(file_path)

            # Check that calculate_file_hash was called only for MD5
            mock_calculate_hash.assert_called_once_with(file_path, 'md5')

            # Check that update_media_file was called with updated hash
            assert mock_db_service.update_media_file.call_count == 1
            updated_file = mock_db_service.update_media_file.call_args[0][0]
            assert updated_file.hashes['md5'] == "new_hash"
