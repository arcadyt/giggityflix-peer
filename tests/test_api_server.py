import json
from datetime import datetime
from pathlib import Path
from unittest import mock

import pytest

from giggityflix_peer.old_api.server import ApiServer
from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType, Screenshot


class TestApiServer:
    """Test suite for the ApiServer class."""

    @pytest.fixture
    def api_server(self):
        """Create an ApiServer instance with mocked services."""
        with mock.patch("giggityflix_peer.api.server.config") as mock_config:
            # Configure the server
            mock_config.peer.http_port = 8080
            mock_config.peer.data_dir = "/tmp"

            # Create the server
            server = ApiServer()

            yield server

    @pytest.mark.asyncio
    async def test_start_and_stop(self, api_server):
        """Test starting and stopping the API server."""
        # Mock the AppRunner and TCPSite
        with mock.patch("giggityflix_peer.api.server.web.AppRunner") as mock_app_runner, \
                mock.patch("giggityflix_peer.api.server.web.TCPSite") as mock_tcp_site:
            # Configure mocks
            mock_runner = mock.AsyncMock()
            mock_site = mock.AsyncMock()
            mock_app_runner.return_value = mock_runner
            mock_tcp_site.return_value = mock_site

            # Start the server
            await api_server.start()

            # Verify
            mock_app_runner.assert_called_once_with(api_server.app)
            mock_runner.setup.assert_called_once()
            mock_tcp_site.assert_called_once_with(mock_runner, "0.0.0.0", 8080)
            mock_site.start.assert_called_once()

            # Stop the server
            await api_server.stop()

            # Verify
            mock_site.stop.assert_called_once()
            mock_runner.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_get_media(self, api_server):
        """Test the handle_get_media method."""
        # Create test media files
        test_files = [
            MediaFile(
                luid="test-luid-1",
                catalog_id="test-catalog-id-1",
                path=Path("/path/to/file1.mp4"),
                relative_path="file1.mp4",
                size_bytes=1024,
                media_type=MediaType.VIDEO,
                status=MediaStatus.READY,
                created_at=datetime.now()
            ),
            MediaFile(
                luid="test-luid-2",
                catalog_id="test-catalog-id-2",
                path=Path("/path/to/file2.mp3"),
                relative_path="file2.mp3",
                size_bytes=512,
                media_type=MediaType.AUDIO,
                status=MediaStatus.READY,
                created_at=datetime.now()
            )
        ]

        # Mock the database service
        with mock.patch("giggityflix_peer.api.server.db_service") as mock_db_service:
            # Configure mock
            mock_db_service.get_all_media_files.return_value = test_files

            # Create a request
            request = mock.MagicMock()

            # Call the handler
            response = await api_server.handle_get_media(request)

            # Verify
            mock_db_service.get_all_media_files.assert_called_once()
            assert response.status == 200

            # Parse the response body
            body = json.loads(response.body)
            assert "media" in body
            assert len(body["media"]) == 2

            # Check the first media item
            media1 = body["media"][0]
            assert media1["luid"] == "test-luid-1"
            assert media1["catalog_id"] == "test-catalog-id-1"
            assert media1["path"] == "/path/to/file1.mp4"
            assert media1["media_type"] == "video"

    @pytest.mark.asyncio
    async def test_handle_get_media_by_id(self, api_server):
        """Test the handle_get_media_by_id method."""
        # Create a test media file
        test_file = MediaFile(
            luid="test-luid",
            catalog_id="test-catalog-id",
            path=Path("/path/to/file.mp4"),
            relative_path="file.mp4",
            size_bytes=1024,
            media_type=MediaType.VIDEO,
            status=MediaStatus.READY,
            created_at=datetime.now(),
            hashes={"md5": "test-hash"}
        )

        # Mock the database service
        with mock.patch("giggityflix_peer.api.server.db_service") as mock_db_service:
            # Configure mock
            mock_db_service.get_media_file.return_value = test_file

            # Create a request with match_info
            request = mock.MagicMock()
            request.match_info = {"luid": "test-luid"}

            # Call the handler
            response = await api_server.handle_get_media_by_id(request)

            # Verify
            mock_db_service.get_media_file.assert_called_once_with("test-luid")
            assert response.status == 200

            # Parse the response body
            body = json.loads(response.body)
            assert "media" in body

            # Check the media item
            media = body["media"]
            assert media["luid"] == "test-luid"
            assert media["catalog_id"] == "test-catalog-id"
            assert media["path"] == "/path/to/file.mp4"
            assert media["media_type"] == "video"
            assert "hashes" in media
            assert media["hashes"]["md5"] == "test-hash"

    @pytest.mark.asyncio
    async def test_handle_get_media_by_id_not_found(self, api_server):
        """Test the handle_get_media_by_id method when the media file is not found."""
        # Mock the database service
        with mock.patch("giggityflix_peer.api.server.db_service") as mock_db_service:
            # Configure mock
            mock_db_service.get_media_file.return_value = None

            # Create a request with match_info
            request = mock.MagicMock()
            request.match_info = {"luid": "nonexistent-luid"}

            # Call the handler
            response = await api_server.handle_get_media_by_id(request)

            # Verify
            mock_db_service.get_media_file.assert_called_once_with("nonexistent-luid")
            assert response.status == 404

            # Parse the response body
            body = json.loads(response.body)
            assert "error" in body

    @pytest.mark.asyncio
    async def test_handle_get_screenshots(self, api_server):
        """Test the handle_get_screenshots method."""
        # Create test screenshots
        test_screenshots = [
            Screenshot(
                id="test-id-1",
                media_luid="test-luid",
                timestamp=10.0,
                path=Path("/path/to/screenshot1.jpg"),
                width=1280,
                height=720,
                created_at=datetime.now()
            ),
            Screenshot(
                id="test-id-2",
                media_luid="test-luid",
                timestamp=20.0,
                path=Path("/path/to/screenshot2.jpg"),
                width=1280,
                height=720,
                created_at=datetime.now()
            )
        ]

        # Mock the database service
        with mock.patch("giggityflix_peer.api.server.db_service") as mock_db_service:
            # Configure mock
            mock_db_service.get_screenshots_for_media.return_value = test_screenshots

            # Create a request with match_info
            request = mock.MagicMock()
            request.match_info = {"luid": "test-luid"}

            # Call the handler
            response = await api_server.handle_get_screenshots(request)

            # Verify
            mock_db_service.get_screenshots_for_media.assert_called_once_with("test-luid")
            assert response.status == 200

            # Parse the response body
            body = json.loads(response.body)
            assert "screenshots" in body
            assert len(body["screenshots"]) == 2

            # Check the first screenshot
            screenshot1 = body["screenshots"][0]
            assert screenshot1["id"] == "test-id-1"
            assert screenshot1["media_luid"] == "test-luid"
            assert screenshot1["timestamp"] == 10.0
            assert screenshot1["path"] == "/path/to/screenshot1.jpg"
            assert screenshot1["url"] == "/screenshots/screenshot1.jpg"
            assert screenshot1["width"] == 1280
            assert screenshot1["height"] == 720

    @pytest.mark.asyncio
    async def test_handle_create_stream(self, api_server):
        """Test the handle_create_stream method."""
        # Mock the stream service
        with mock.patch("giggityflix_peer.api.server.stream_service") as mock_stream_service:
            # Configure mock
            from aiortc import RTCSessionDescription
            mock_offer = RTCSessionDescription(sdp="test-sdp", type="offer")
            mock_stream_service.create_session.return_value = ("test-session-id", mock_offer)

            # Create a request with match_info
            request = mock.MagicMock()
            request.match_info = {"luid": "test-luid"}

            # Call the handler
            response = await api_server.handle_create_stream(request)

            # Verify
            mock_stream_service.create_session.assert_called_once_with("test-luid")
            assert response.status == 200

            # Parse the response body
            body = json.loads(response.body)
            assert "session_id" in body
            assert body["session_id"] == "test-session-id"
            assert "offer" in body
            assert body["offer"]["sdp"] == "test-sdp"
            assert body["offer"]["type"] == "offer"

    @pytest.mark.asyncio
    async def test_handle_create_stream_failure(self, api_server):
        """Test the handle_create_stream method when creation fails."""
        # Mock the stream service
        with mock.patch("giggityflix_peer.api.server.stream_service") as mock_stream_service:
            # Configure mock
            mock_stream_service.create_session.return_value = None

            # Create a request with match_info
            request = mock.MagicMock()
            request.match_info = {"luid": "test-luid"}

            # Call the handler
            response = await api_server.handle_create_stream(request)

            # Verify
            mock_stream_service.create_session.assert_called_once_with("test-luid")
            assert response.status == 500

            # Parse the response body
            body = json.loads(response.body)
            assert "error" in body

    @pytest.mark.asyncio
    async def test_handle_stream_answer(self, api_server):
        """Test the handle_stream_answer method."""
        # Mock the stream service
        with mock.patch("giggityflix_peer.api.server.stream_service") as mock_stream_service:
            # Configure mock
            mock_stream_service.handle_answer.return_value = True

            # Create a request with match_info and body
            request = mock.MagicMock()
            request.match_info = {"session_id": "test-session-id"}
            request.json.return_value = {
                "sdp": "test-sdp",
                "type": "answer"
            }

            # Call the handler
            response = await api_server.handle_stream_answer(request)

            # Verify
            mock_stream_service.handle_answer.assert_called_once_with(
                "test-session-id", "test-sdp", "answer"
            )
            assert response.status == 200

            # Parse the response body
            body = json.loads(response.body)
            assert body["status"] == "ok"

    @pytest.mark.asyncio
    async def test_handle_stream_answer_missing_data(self, api_server):
        """Test the handle_stream_answer method with missing data."""
        # Create a request with match_info and incomplete body
        request = mock.MagicMock()
        request.match_info = {"session_id": "test-session-id"}
        request.json.return_value = {
            # Missing 'sdp' field
            "type": "answer"
        }

        # Call the handler
        response = await api_server.handle_stream_answer(request)

        # Verify
        assert response.status == 400

        # Parse the response body
        body = json.loads(response.body)
        assert "error" in body

    @pytest.mark.asyncio
    async def test_handle_close_stream(self, api_server):
        """Test the handle_close_stream method."""
        # Mock the stream service
        with mock.patch("giggityflix_peer.api.server.stream_service") as mock_stream_service:
            # Configure mock
            mock_stream_service.close_session.return_value = True

            # Create a request with match_info
            request = mock.MagicMock()
            request.match_info = {"session_id": "test-session-id"}

            # Call the handler
            response = await api_server.handle_close_stream(request)

            # Verify
            mock_stream_service.close_session.assert_called_once_with("test-session-id")
            assert response.status == 200

            # Parse the response body
            body = json.loads(response.body)
            assert body["status"] == "ok"

    @pytest.mark.asyncio
    async def test_handle_capture_screenshots(self, api_server):
        """Test the handle_capture_screenshots method."""
        # Create test media file
        test_file = MediaFile(
            luid="test-luid",
            catalog_id="test-catalog-id",
            path=Path("/path/to/file.mp4"),
            media_type=MediaType.VIDEO,
            size_bytes=1024,
            status=MediaStatus.READY
        )

        # Create test screenshots
        test_screenshots = [
            Screenshot(
                id="test-id-1",
                media_luid="test-luid",
                timestamp=10.0,
                path=Path("/path/to/screenshot1.jpg"),
                width=1280,
                height=720,
                created_at=datetime.now()
            ),
            Screenshot(
                id="test-id-2",
                media_luid="test-luid",
                timestamp=20.0,
                path=Path("/path/to/screenshot2.jpg"),
                width=1280,
                height=720,
                created_at=datetime.now()
            )
        ]

        # Mock the services
        with mock.patch("giggityflix_peer.api.server.db_service") as mock_db_service, \
                mock.patch("giggityflix_peer.api.server.screenshot_service") as mock_screenshot_service:
            # Configure mocks
            mock_db_service.get_media_file.return_value = test_file
            mock_screenshot_service.capture_screenshots.return_value = test_screenshots

            # Create a request with match_info and query
            request = mock.MagicMock()
            request.match_info = {"luid": "test-luid"}
            request.query = {"quantity": "2"}

            # Call the handler
            response = await api_server.handle_capture_screenshots(request)

            # Verify
            mock_db_service.get_media_file.assert_called_once_with("test-luid")
            mock_screenshot_service.capture_screenshots.assert_called_once_with(test_file, 2)
            assert response.status == 200

            # Parse the response body
            body = json.loads(response.body)
            assert "screenshots" in body
            assert len(body["screenshots"]) == 2
