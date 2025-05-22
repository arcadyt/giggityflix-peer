import tempfile
from pathlib import Path
from unittest import mock

import pytest
from aiortc import RTCSessionDescription

from giggityflix_peer.models.media import MediaFile, MediaType, MediaStatus
from giggityflix_peer.old_services.db_service import db_service
from giggityflix_peer.apps.media.fixme_services.stream_service import StreamService, StreamSession


@pytest.fixture
def test_media_file():
    """Create a test media file."""
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_file:
        # Create a media file object pointing to the temporary file
        media_file = MediaFile(
            luid="test-luid",
            catalog_id="test-catalog-id",
            path=Path(tmp_file.name),
            size_bytes=0,
            media_type=MediaType.VIDEO,
            status=MediaStatus.READY
        )

        yield media_file


@pytest.mark.asyncio
async def test_stream_session_creation(test_media_file):
    """Test creating a stream session."""
    # Create a session
    session = StreamSession("test-session", test_media_file)

    # Check session properties
    assert session.session_id == "test-session"
    assert session.media_file == test_media_file
    assert session.peer_connection is None
    assert session.player is None

    # Mock the create offer method to avoid actual WebRTC
    with mock.patch.object(StreamSession, 'create_offer', autospec=True) as mock_create_offer:
        # Mock return value
        mock_create_offer.return_value = RTCSessionDescription(sdp="test", type="offer")

        # Create an offer
        offer = await session.create_offer()

        # Check that the method was called
        mock_create_offer.assert_called_once()

        # Check the offer
        assert offer.sdp == "test"
        assert offer.type == "offer"


@pytest.mark.asyncio
async def test_stream_service(test_media_file):
    """Test the stream service."""
    # Create a stream service
    service = StreamService()

    # Mock db_service.get_media_file to return our test file
    with mock.patch.object(db_service, 'get_media_file', autospec=True) as mock_get_media_file, \
            mock.patch.object(db_service, 'increment_view_count', autospec=True) as mock_increment_view_count, \
            mock.patch.object(StreamSession, 'create_offer', autospec=True) as mock_create_offer:

        # Set up mocks
        mock_get_media_file.return_value = test_media_file
        mock_create_offer.return_value = RTCSessionDescription(sdp="test", type="offer")

        # Start the service
        await service.start()

        try:
            # Create a session
            result = await service.create_session("test-luid")

            # Check that the methods were called
            mock_get_media_file.assert_called_once_with("test-luid")
            mock_increment_view_count.assert_called_once_with("test-luid")

            # Check the result
            assert result is not None
            session_id, offer = result
            assert isinstance(session_id, str)
            assert offer.sdp == "test"
            assert offer.type == "offer"

            # Check that the session was stored
            assert session_id in service.active_sessions

            # Get the session
            session = await service.get_session(session_id)
            assert session is not None
            assert session.session_id == session_id
            assert session.media_file == test_media_file

            # Close the session
            with mock.patch.object(StreamSession, 'close', autospec=True) as mock_close:
                success = await service.close_session(session_id)
                assert success
                mock_close.assert_called_once()
                assert session_id not in service.active_sessions

        finally:
            # Stop the service
            await service.stop()
