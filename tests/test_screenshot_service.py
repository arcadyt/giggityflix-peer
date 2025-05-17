import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import cv2
import numpy as np
import pytest

from giggityflix_peer.models.media import MediaFile, MediaType, MediaStatus, Screenshot
from giggityflix_peer.services.screenshot_service import ScreenshotService


@pytest.fixture
def media_file():
    """Create a mock media file."""
    return MediaFile(
        luid="test-luid",
        path=Path("test_video.mp4"),
        size_bytes=1000,
        media_type=MediaType.VIDEO,
        status=MediaStatus.READY,
        duration_seconds=100.0,
        framerate=30.0
    )


@pytest.fixture
def screenshot_service():
    """Create a screenshot service."""
    return ScreenshotService()


# Move this fixture outside the class
@pytest.fixture
def mock_video_capture(mocker):
    """Create a mocked video capture object with synthetic frames."""
    # Video properties
    width, height = 16, 9
    fps = 30
    num_frames = 100

    # Create synthetic frames
    frames = []
    for i in range(num_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = i % 256  # Blue channel
        frame[:, :, 1] = (i * 2) % 256  # Green channel
        frame[:, :, 2] = (i * 3) % 256  # Red channel
        frames.append(frame)

    # Mock VideoCapture object
    mock_video = mocker.MagicMock()
    mock_video.isOpened.return_value = True

    # Set up metadata properties
    mock_video.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_WIDTH: width,
        cv2.CAP_PROP_FRAME_HEIGHT: height,
        cv2.CAP_PROP_FPS: fps,
        cv2.CAP_PROP_FRAME_COUNT: num_frames,
        cv2.CAP_PROP_FOURCC: cv2.VideoWriter_fourcc(*'XVID'),
        cv2.CAP_PROP_BITRATE: 90000
    }.get(prop, 0)

    # Set up read method to return frames sequentially
    read_count = 0

    def mock_read():
        nonlocal read_count
        if read_count < len(frames):
            frame = frames[read_count]
            read_count += 1
            return True, frame
        return False, None

    mock_video.read.side_effect = mock_read

    # Mock CV2 VideoCapture constructor
    mocker.patch('cv2.VideoCapture', return_value=mock_video)

    # Mock Path.is_file to return True
    mocker.patch('pathlib.Path.is_file', return_value=True)

    # Return metadata for assertions
    video_metadata = {
        'width': width,
        'height': height,
        'fps': fps,
        'num_frames': num_frames,
        'mock_video': mock_video
    }

    return video_metadata


@pytest.mark.asyncio
class TestScreenshotService:

    @pytest.mark.skip(reason="Issue with mocking aiohttp nested async context managers")
    async def test_upload_screenshots(self, screenshot_service):
        """Test uploading screenshots."""
        # Create test screenshots with image data
        screenshots = []
        for i in range(3):
            screenshot = Screenshot(
                id=f"test-id-{i}",
                media_luid="test-luid",
                timestamp=float(i),
                path=Path(f"MEMORY_test{i}.jpg"),
                width=640,
                height=480
            )

        # This is a better approach to mock the full functionality
        # Mock the entire ClientSession context manager
        mock_client_session = MagicMock()
        # Mock the session.__aenter__ to return itself
        mock_client_session.__aenter__ = AsyncMock(return_value=mock_client_session)
        # Mock the session.__aexit__ to do nothing
        mock_client_session.__aexit__ = AsyncMock(return_value=None)

        # Mock the response from post
        mock_response = MagicMock()
        mock_response.status = 200
        # Mock the response.__aenter__ to return itself
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        # Mock the response.__aexit__ to do nothing
        mock_response.__aexit__ = AsyncMock(return_value=None)

        # Setup post method to return the mock response
        mock_client_session.post = AsyncMock(return_value=mock_response)

        # Mock the ClientSession constructor to return our mock
        with patch('aiohttp.ClientSession', return_value=mock_client_session):
            result = await screenshot_service.upload_screenshots(
                screenshots,
                "http://example.com/upload",
                "test-token"
            )

            assert result is True

            # Check that post was called for each screenshot
            assert mock_client_session.post.call_count == 3

    async def test_capture_screenshots_synthetic(self, screenshot_service, mock_video_capture):
        """Test capturing screenshots using a synthetic video file with mocks."""

        # Use the mocked video fixture - everything is already set up
        width = mock_video_capture['width']
        height = mock_video_capture['height']
        fps = mock_video_capture['fps']
        num_frames = mock_video_capture['num_frames']

        # Capture screenshots with mocked video
        screenshots, metadata = await screenshot_service.capture_screenshots("mock_video_path.mp4", 5)

        # Verify results
        assert len(screenshots) == 5
        assert all(len(s) > 0 for s in screenshots)

        # Verify metadata
        assert metadata.width == width
        assert metadata.height == height
        assert metadata.frame_rate == fps
        assert metadata.frames == num_frames

    # Example of another test using the same fixture
    async def test_capture_single_screenshot(self, screenshot_service, mock_video_capture):
        """Test capturing a single screenshot."""

        # Capture just one screenshot
        screenshots, metadata = await screenshot_service.capture_screenshots("mock_video_path.mp4", 1)

        # Verify results
        assert len(screenshots) == 1
        assert len(screenshots[0]) > 0

        # Verify that the mock was used correctly
        mock_video = mock_video_capture['mock_video']
        # For example, assert that read() was called at least once
        assert mock_video.read.called

    async def test_capture_screenshots_real_file(self, screenshot_service):
        """Test capturing screenshots from a real video file."""
        file_path = ''

        # Skip test if file doesn't exist
        if not os.path.exists(file_path):
            pytest.skip(f"Test video file not found: {file_path}")

        expected_qty = 5
        screenshots = await screenshot_service.capture_screenshots(file_path, expected_qty)

        # Don't use cv2.imshow in automated tests
        # Instead, verify the screenshots are valid JPEG data
        assert len(screenshots) == expected_qty

        # Basic validation of screenshots
        for screenshot in screenshots:
            assert len(screenshot) > 0
            # Optional: verify it's a valid image
            np_array = np.frombuffer(screenshot, np.uint8)
            img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

            assert img is not None
            assert img.shape[0] > 0  # height
            assert img.shape[1] > 0  # width

            cv2.imshow('Preview', img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()


if __name__ == "__main__":
    pytest.main()
