import asyncio
from pathlib import Path
from unittest import mock

import pytest

from giggityflix_peer.peer_app import PeerApp


class TestPeerApp:
    """Test suite for the PeerApp class."""

    @pytest.fixture
    def peer_app(self):
        """Create a PeerApp instance with mocked dependencies."""
        with mock.patch("giggityflix_peer.peer_app.config") as mock_config, \
                mock.patch("giggityflix_peer.peer_app.db") as mock_db, \
                mock.patch("giggityflix_peer.peer_app.EdgeClient") as mock_edge_client_cls, \
                mock.patch("giggityflix_peer.peer_app.MediaScanner") as mock_scanner_cls, \
                mock.patch("giggityflix_peer.peer_app.stream_service") as mock_stream_service, \
                mock.patch("giggityflix_peer.peer_app.api_server") as mock_api_server, \
                mock.patch("giggityflix_peer.peer_app.db_service") as mock_db_service, \
                mock.patch("os.makedirs") as mock_makedirs:
            # Configure mocks
            mock_config.peer.peer_id = "test-peer-id"
            mock_config.peer.auto_generate_id = False
            mock_config.peer.data_dir = "/tmp/test-data"

            # Create mock instances
            mock_edge_client = mock.AsyncMock()
            mock_scanner = mock.AsyncMock()

            # Configure class mocks to return our instances
            mock_edge_client_cls.return_value = mock_edge_client
            mock_scanner_cls.return_value = mock_scanner

            # Create the app
            app = PeerApp()

            # Store mock objects for access in tests
            app._mock_db = mock_db
            app._mock_edge_client = mock_edge_client
            app._mock_scanner = mock_scanner
            app._mock_stream_service = mock_stream_service
            app._mock_api_server = mock_api_server
            app._mock_db_service = mock_db_service

            yield app

    def test_init(self, peer_app):
        """Test PeerApp initialization."""
        # Check attributes
        assert peer_app.peer_id == "test-peer-id"
        assert peer_app.data_dir == Path("/tmp/test-data")
        assert not peer_app._running
        assert isinstance(peer_app._stop_event, asyncio.Event)

        # Check that dependencies were correctly initialized
        assert peer_app.edge_client is peer_app._mock_edge_client
        assert peer_app.media_scanner is peer_app._mock_scanner

    @pytest.mark.asyncio
    async def test_start_and_stop(self, peer_app):
        """Test starting and stopping the peer app."""
        # Start the app
        await peer_app.start()

        # Check that dependencies were started
        peer_app._mock_db.initialize.assert_called_once()
        peer_app._mock_edge_client.connect.assert_called_once()
        peer_app._mock_scanner.start.assert_called_once()
        peer_app._mock_stream_service.start.assert_called_once()
        peer_app._mock_api_server.start.assert_called_once()

        # Check that the app is running
        assert peer_app._running

        # Stop the app
        await peer_app.stop()

        # Check that dependencies were stopped
        peer_app._mock_api_server.stop.assert_called_once()
        peer_app._mock_stream_service.stop.assert_called_once()
        peer_app._mock_scanner.stop.assert_called_once()
        peer_app._mock_edge_client.disconnect.assert_called_once()
        peer_app._mock_db.close.assert_called_once()

        # Check that the app is stopped
        assert not peer_app._running
        # Check that the stop event is set
        assert peer_app._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_start_edge_connection_failure(self, peer_app):
        """Test starting the app when edge connection fails."""
        # Configure edge client to fail
        peer_app._mock_edge_client.connect.return_value = False

        # Start the app
        await peer_app.start()

        # Check that the app still starts
        assert peer_app._running

        # Check that dependencies were still started
        peer_app._mock_db.initialize.assert_called_once()
        peer_app._mock_scanner.start.assert_called_once()
        peer_app._mock_stream_service.start.assert_called_once()
        peer_app._mock_api_server.start.assert_called_once()

        # Clean up
        await peer_app.stop()

    @pytest.mark.asyncio
    async def test_scan_media(self, peer_app):
        """Test triggering a media scan."""
        # Set the app as running
        peer_app._running = True

        # Call the method
        await peer_app.scan_media()

        # Check that the scanner was called
        peer_app._mock_scanner.scan_now.assert_called_once()

    @pytest.mark.asyncio
    async def test_scan_media_not_running(self, peer_app):
        """Test triggering a media scan when the app is not running."""
        # Call the method
        await peer_app.scan_media()

        # Check that the scanner was not called
        peer_app._mock_scanner.scan_now.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_catalog(self, peer_app):
        """Test updating the catalog."""
        # Set the app as running
        peer_app._running = True

        # Create test media files
        media_files = [mock.MagicMock(), mock.MagicMock()]
        peer_app._mock_db_service.get_all_media_files.return_value = media_files

        # Configure edge client
        peer_app._mock_edge_client.update_catalog.return_value = True

        # Call the method
        await peer_app.update_catalog()

        # Check that services were called
        peer_app._mock_db_service.get_all_media_files.assert_called_once()
        peer_app._mock_edge_client.update_catalog.assert_called_once_with(media_files)

        # Check that catalog IDs were updated
        assert peer_app._mock_db_service.update_media_catalog_id.call_count == len(media_files)

    @pytest.mark.asyncio
    async def test_update_catalog_no_files(self, peer_app):
        """Test updating the catalog when there are no media files."""
        # Set the app as running
        peer_app._running = True

        # Configure database service
        peer_app._mock_db_service.get_all_media_files.return_value = []

        # Call the method
        await peer_app.update_catalog()

        # Check that edge client was not called
        peer_app._mock_edge_client.update_catalog.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_for_stop(self, peer_app):
        """Test waiting for the app to stop."""

        # Create a task to set the stop event after a delay
        async def set_stop_event():
            await asyncio.sleep(0.1)
            peer_app._stop_event.set()

        # Start the task
        task = asyncio.create_task(set_stop_event())

        # Wait for the stop event
        await peer_app.wait_for_stop()

        # Check that the stop event was set
        assert peer_app._stop_event.is_set()

        # Clean up
        await task

    def test_is_running(self, peer_app):
        """Test the is_running method."""
        # Initially not running
        assert not peer_app.is_running()

        # Set as running
        peer_app._running = True
        assert peer_app.is_running()

        # Set as not running
        peer_app._running = False
        assert not peer_app.is_running()


@pytest.mark.asyncio
async def test_auto_generate_peer_id():
    """Test automatic generation of peer ID."""
    with mock.patch("giggityflix_peer.peer_app.config") as mock_config, \
            mock.patch("giggityflix_peer.peer_app.db") as mock_db, \
            mock.patch("giggityflix_peer.peer_app.EdgeClient") as mock_edge_client_cls, \
            mock.patch("giggityflix_peer.peer_app.MediaScanner") as mock_scanner_cls, \
            mock.patch("giggityflix_peer.peer_app.uuid.uuid4", return_value="generated-uuid"), \
            mock.patch("os.makedirs"):
        # Configure mock
        mock_config.peer.peer_id = ""
        mock_config.peer.auto_generate_id = True
        mock_config.peer.data_dir = "/tmp/test-data"

        # Create app
        app = PeerApp()

        # Check that ID was generated
        assert app.peer_id == "generated-uuid"
