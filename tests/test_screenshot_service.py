import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType
from giggityflix_peer.services.screenshot_service import ScreenshotService


class TestScreenshotService:
    """Test suite for the ScreenshotService class."""

    @pytest.fixture
    def screenshot_service(self):
        """Create a ScreenshotService instance."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("giggityflix_peer.services.screenshot_service.config") as mock_config:
                # Configure the service
                mock_config.peer.data_dir = temp_dir

                # Create the service
                service = ScreenshotService()

                # Ensure the screenshot directory exists
                os.makedirs(service.screenshot_dir, exist_ok=True)

                yield service

    @pytest.fixture
    def test_media_file(self):
        """Create a test media file."""
        with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_file:
            # Write some test data to simulate a video file
            tmp_file.write(b"test video data")
            tmp_file.flush()

            # Create a media file object
            media_file = MediaFile(
                luid="test-luid",
                catalog_id="test-catalog-id",
                path=Path(tmp_file.name),
                relative_path="test.mp4",
                size_bytes=len(b"test video data"),
                media_type=MediaType.VIDEO,
                status=MediaStatus.READY,
                duration_seconds=60.0  # 1 minute
            )

            yield media_file

    def test_calculate_screenshot_timestamps(self, screenshot_service, test_media_file):
        """Test calculating screenshot timestamps."""
        # Test with 1 screenshot
        timestamps = screenshot_service._calculate_screenshot_timestamps(test_media_file, 1)
        assert len(timestamps) == 1
        assert timestamps[0] == 30.0  # Middle of the video

        # Test with 3 screenshots
        timestamps = screenshot_service._calculate_screenshot_timestamps(test_media_file, 3)
        assert len(timestamps) == 3
        assert timestamps[0] == 3.0  # 5% + 0% of usable duration
        assert timestamps[1] == 30.0  # 5% + 50% of usable duration
        assert timestamps[2] == 57.0  # 5% + 100% of usable duration

        # Test with no duration
        test_media_file.duration_seconds = None
        timestamps = screenshot_service._calculate_screenshot_timestamps(test_media_file, 1)
        assert len(timestamps) == 1
        assert timestamps[0] == 30.0  # Uses default 60s duration

    @pytest.mark.asyncio
    async def test_capture_screenshots(self, screenshot_service, test_media_file):
        """Test capturing screenshots."""
        # Mock the capture_screenshot method to avoid actually capturing screenshots
        with mock.patch.object(screenshot_service, "_capture_screenshot") as mock_capture, \
                mock.patch("giggityflix_peer.services.db_service.db_service") as mock_db_service:
            # Configure mocks
            mock_capture.return_value = (True, 1280, 720)

            # Call the method
            screenshots = await screenshot_service.capture_screenshots(test_media_file, 3)

            # Verify
            assert len(screenshots) == 3
            assert mock_capture.call_count == 3
            assert mock_db_service.add_screenshot.call_count == 3

            # Check the screenshot objects
            for i, screenshot in enumerate(screenshots):
                assert screenshot.media_luid == "test-luid"
                assert screenshot.width == 1280
                assert screenshot.height == 720
                assert screenshot.path.parent == screenshot_service.screenshot_dir
                assert test_media_file.luid in str(screenshot.path)

    @pytest.mark.asyncio
    async def test_capture_screenshots_nonexistent_file(self, screenshot_service):
        """Test capturing screenshots for a nonexistent file."""
        # Create a media file with a nonexistent path
        media_file = MediaFile(
            luid="test-luid",
            catalog_id="test-catalog-id",
            path=Path("/nonexistent/path.mp4"),
            media_type=MediaType.VIDEO,
            size_bytes=1024,
            status=MediaStatus.READY
        )

        # Call the method
        screenshots = await screenshot_service.capture_screenshots(media_file, 3)

        # Verify
        assert len(screenshots) == 0

    @pytest.mark.asyncio
    async def test_capture_screenshots_non_video(self, screenshot_service, test_media_file):
        """Test capturing screenshots for a non-video file."""
        # Modify the media type
        test_media_file.media_type = MediaType.AUDIO

        # Call the method
        screenshots = await screenshot_service.capture_screenshots(test_media_file, 3)

        # Verify
        assert len(screenshots) == 0

    @pytest.mark.asyncio
    async def test_upload_screenshots(self, screenshot_service):
        """Test uploading screenshots."""
        # Create some test screenshot files
        screenshot_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                tmp_file.write(b"test screenshot data")
                tmp_file.flush()
                screenshot_files.append(Path(tmp_file.name))

        try:
            # Create screenshot objects
            screenshots = []
            for i, path in enumerate(screenshot_files):
                from giggityflix_peer.models.media import Screenshot
                screenshot = Screenshot(
                    id=f"test-id-{i}",
                    media_luid="test-luid",
                    timestamp=i * 10.0,
                    path=path,
                    width=1280,
                    height=720
                )
                screenshots.append(screenshot)

            # Mock the aiohttp.ClientSession
            mock_response = mock.AsyncMock()
            mock_response.status = 200
            mock_session = mock.AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.post.return_value.__aenter__.return_value = mock_response

            # Mock the aiohttp.FormData
            mock_form = mock.MagicMock()

            with mock.patch("giggityflix_peer.services.screenshot_service.aiohttp.ClientSession",
                            return_value=mock_session), \
                    mock.patch("giggityflix_peer.services.screenshot_service.aiohttp.FormData",
                               return_value=mock_form):

                # Call the method
                success = await screenshot_service.upload_screenshots(
                    screenshots, "https://example.com/upload", "test-token"
                )

                # Verify
                assert success is True
                assert mock_session.post.call_count == 3

                # Check headers and form data
                for call in mock_session.post.call_args_list:
                    args, kwargs = call
                    assert args[0] == "https://example.com/upload"
                    assert kwargs["headers"] == {"Authorization": "Bearer test-token"}
                    assert kwargs["data"] == mock_form

        finally:
            # Clean up
            for path in screenshot_files:
                if path.exists():
                    path.unlink()

    @pytest.mark.asyncio
    async def test_capture_screenshot(self, screenshot_service, test_media_file):
        """Test capturing a single screenshot."""
        # Since this test would normally require OpenCV, we'll just test the placeholder path
        with mock.patch("giggityflix_peer.services.screenshot_service.OPENCV_AVAILABLE", False):
            # Call the method with timestamp 30.0
            output_path = screenshot_service.screenshot_dir / "test.jpg"
            success, width, height = await screenshot_service._capture_screenshot(
                test_media_file.path, output_path, 30.0
            )

            # Verify
            assert success is True
            assert width == 640
            assert height == 480
            assert output_path.exists()

            # Clean up
            output_path.unlink()
