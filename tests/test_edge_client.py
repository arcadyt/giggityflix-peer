import asyncio
from unittest import mock

import pytest
from giggityflix_grpc_peer import peer_edge_pb2 as pb2

from giggityflix_peer.models.media import MediaFile, MediaType, MediaStatus
from giggityflix_peer.services.edge_client import EdgeClient


class TestEdgeClient:
    """Test suite for the EdgeClient class."""

    @pytest.fixture
    def edge_client(self):
        """Create an EdgeClient instance."""
        with mock.patch("giggityflix_peer.services.edge_client.config") as mock_config:
            # Configure client
            mock_config.grpc.edge_address = "localhost:50051"
            mock_config.grpc.reconnect_interval_sec = 1
            mock_config.grpc.max_reconnect_attempts = 2
            mock_config.grpc.heartbeat_interval_sec = 1
            mock_config.grpc.timeout_sec = 2
            mock_config.grpc.use_tls = False

            # Create client
            client = EdgeClient("test-peer-id")

            yield client

            # Clean up
            loop = asyncio.get_event_loop()
            if client._connected:
                loop.run_until_complete(client.disconnect())

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self, edge_client):
        """Test connecting and disconnecting from the Edge Service."""
        # Mock the grpc.aio module
        with mock.patch("giggityflix_peer.services.edge_client.grpc.aio") as mock_grpc_aio, \
                mock.patch.object(edge_client, "_register", return_value=True), \
                mock.patch.object(edge_client, "_receive_messages"), \
                mock.patch.object(edge_client, "_send_heartbeats"):
            # Mock the channel and stream
            mock_channel = mock.AsyncMock()
            mock_stub = mock.MagicMock()
            mock_stream = mock.AsyncMock()

            # Configure mocks
            mock_grpc_aio.insecure_channel.return_value = mock_channel
            mock_stub.message.return_value = mock_stream

            # Hook up the stub creation
            edge_client._stub = mock_stub

            # Connect
            result = await edge_client.connect()

            # Verify
            assert result is True
            assert edge_client._connected is True
            mock_grpc_aio.insecure_channel.assert_called_once_with("localhost:50051")

            # Disconnect
            await edge_client.disconnect()

            # Verify
            assert edge_client._connected is False
            mock_channel.close.assert_called_once()
            mock_stream.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconnect(self, edge_client):
        """Test reconnecting to the Edge Service."""
        # Mock the connect and disconnect methods
        with mock.patch.object(edge_client, "connect", side_effect=[False, True]) as mock_connect, \
                mock.patch.object(edge_client, "disconnect") as mock_disconnect, \
                mock.patch("giggityflix_peer.services.edge_client.asyncio.sleep") as mock_sleep:
            # Call reconnect
            result = await edge_client.reconnect()

            # Verify
            assert result is True
            assert mock_connect.call_count == 2
            mock_disconnect.assert_called_once()
            mock_sleep.assert_called_once_with(1)  # reconnect_interval_sec

    @pytest.mark.asyncio
    async def test_reconnect_fails(self, edge_client):
        """Test reconnecting to the Edge Service when all attempts fail."""
        # Mock the connect and disconnect methods
        with mock.patch.object(edge_client, "connect", return_value=False) as mock_connect, \
                mock.patch.object(edge_client, "disconnect") as mock_disconnect, \
                mock.patch("giggityflix_peer.services.edge_client.asyncio.sleep") as mock_sleep:
            # Call reconnect
            result = await edge_client.reconnect()

            # Verify
            assert result is False
            assert mock_connect.call_count == 2  # max_reconnect_attempts
            mock_disconnect.assert_called_once()
            mock_sleep.assert_called_once_with(1)  # reconnect_interval_sec

    @pytest.mark.asyncio
    async def test_register(self, edge_client):
        """Test registering with the Edge Service."""
        # Set up edge_client
        edge_client._stream = mock.AsyncMock()

        # Create a registration response
        response = pb2.EdgeMessage(
            request_id="test-request-id",
            registration_response=pb2.PeerRegistrationResponse(
                peer_name="test-peer-id",
                edge_name="test-edge",
                success=True
            )
        )

        # Mock future for the response
        future = asyncio.Future()
        future.set_result(response)

        with mock.patch.object(edge_client, "_pending_requests", {}) as mock_pending_requests, \
                mock.patch("giggityflix_peer.services.edge_client.uuid.uuid4", return_value="test-request-id"), \
                mock.patch("giggityflix_peer.services.edge_client.asyncio.wait_for", return_value=response):
            # Call the _register method
            result = await edge_client._register()

            # Verify
            assert result is True
            assert edge_client._stream.write.call_count == 1

            # Get the message that was written
            message_arg = edge_client._stream.write.call_args[0][0]
            assert message_arg.request_id == "test-request-id"
            assert message_arg.HasField("registration_request")
            assert message_arg.registration_request.peer_name == "test-peer-id"

    @pytest.mark.asyncio
    async def test_register_failure(self, edge_client):
        """Test registration failure."""
        # Set up edge_client
        edge_client._stream = mock.AsyncMock()

        # Create a registration response
        response = pb2.EdgeMessage(
            request_id="test-request-id",
            registration_response=pb2.PeerRegistrationResponse(
                peer_name="test-peer-id",
                edge_name="test-edge",
                success=False  # Failed
            )
        )

        with mock.patch.object(edge_client, "_pending_requests", {}), \
                mock.patch("giggityflix_peer.services.edge_client.uuid.uuid4", return_value="test-request-id"), \
                mock.patch("giggityflix_peer.services.edge_client.asyncio.wait_for", return_value=response):
            # Call the _register method
            result = await edge_client._register()

            # Verify
            assert result is False

    @pytest.mark.asyncio
    async def test_register_timeout(self, edge_client):
        """Test registration timeout."""
        # Set up edge_client
        edge_client._stream = mock.AsyncMock()

        with mock.patch.object(edge_client, "_pending_requests", {}), \
                mock.patch("giggityflix_peer.services.edge_client.uuid.uuid4", return_value="test-request-id"), \
                mock.patch("giggityflix_peer.services.edge_client.asyncio.wait_for",
                           side_effect=asyncio.TimeoutError):
            # Call the _register method
            result = await edge_client._register()

            # Verify
            assert result is False

    @pytest.mark.asyncio
    async def test_update_catalog(self, edge_client):
        """Test updating the catalog."""
        # Set up edge_client
        edge_client._stream = mock.AsyncMock()
        edge_client._connected = True

        # Create test media files
        media_file1 = MediaFile(
            luid="test-luid-1",
            path="/path/to/file1.mp4",
            relative_path="file1.mp4",
            size_bytes=1024,
            media_type=MediaType.VIDEO,
            status=MediaStatus.READY
        )

        media_file2 = MediaFile(
            luid="test-luid-2",
            path="/path/to/file2.mp3",
            relative_path="file2.mp3",
            size_bytes=512,
            media_type=MediaType.AUDIO,
            status=MediaStatus.READY
        )

        # Create a response with assigned catalog IDs
        response = pb2.EdgeMessage(
            request_id="test-request-id",
            batch_file_offer_response=pb2.BatchFileOfferResponse(
                files=[
                    pb2.FileOfferResult(
                        peer_luid="test-luid-1",
                        catalog_uuid="catalog-id-1"
                    ),
                    pb2.FileOfferResult(
                        peer_luid="test-luid-2",
                        catalog_uuid="catalog-id-2"
                    )
                ]
            )
        )

        with mock.patch.object(edge_client, "_pending_requests", {}), \
                mock.patch("giggityflix_peer.services.edge_client.uuid.uuid4", return_value="test-request-id"), \
                mock.patch("giggityflix_peer.services.edge_client.asyncio.wait_for", return_value=response):
            # Call update_catalog
            result = await edge_client.update_catalog([media_file1, media_file2])

            # Verify
            assert result is True
            assert edge_client._stream.write.call_count == 1

            # Check that catalog IDs were assigned
            assert media_file1.catalog_id == "catalog-id-1"
            assert media_file2.catalog_id == "catalog-id-2"

            # Get the message that was written
            message_arg = edge_client._stream.write.call_args[0][0]
            assert message_arg.request_id == "test-request-id"
            assert message_arg.HasField("batch_file_offer_request")
            assert len(message_arg.batch_file_offer_request.files) == 2

    @pytest.mark.asyncio
    async def test_process_edge_message(self, edge_client):
        """Test processing edge messages."""
        # Mock the handler methods
        with mock.patch.object(edge_client, "handle_file_delete_request") as mock_delete, \
                mock.patch.object(edge_client, "handle_file_hash_request") as mock_hash, \
                mock.patch.object(edge_client, "handle_file_remap_request") as mock_remap, \
                mock.patch.object(edge_client, "handle_screenshot_capture_request") as mock_screenshot:
            # Call with a delete request
            delete_message = pb2.EdgeMessage(
                request_id="test-request-id",
                file_delete_request=pb2.FileDeleteRequest(
                    catalog_uuids=["test-catalog-id"]
                )
            )
            await edge_client._process_edge_message(delete_message)
            mock_delete.assert_called_once_with(
                delete_message.file_delete_request,
                "test-request-id"
            )

            # Call with a hash request
            hash_message = pb2.EdgeMessage(
                request_id="test-request-id",
                file_hash_request=pb2.FileHashRequest(
                    catalog_uuid="test-catalog-id",
                    hash_types=["md5"]
                )
            )
            await edge_client._process_edge_message(hash_message)
            mock_hash.assert_called_once_with(
                hash_message.file_hash_request,
                "test-request-id"
            )

            # Call with a remap request
            remap_message = pb2.EdgeMessage(
                request_id="test-request-id",
                file_remap_request=pb2.FileRemapRequest(
                    old_catalog_uuid="old-id",
                    new_catalog_uuid="new-id"
                )
            )
            await edge_client._process_edge_message(remap_message)
            mock_remap.assert_called_once_with(
                remap_message.file_remap_request,
                "test-request-id"
            )

            # Call with a screenshot request
            screenshot_message = pb2.EdgeMessage(
                request_id="test-request-id",
                screenshot_capture_request=pb2.ScreenshotCaptureRequest(
                    catalog_uuid="test-catalog-id",
                    quantity=3,
                    upload_token="test-token",
                    upload_endpoint="/test/endpoint"
                )
            )
            await edge_client._process_edge_message(screenshot_message)
            mock_screenshot.assert_called_once_with(
                screenshot_message.screenshot_capture_request,
                "test-request-id"
            )

    @pytest.mark.asyncio
    async def test_pending_request_resolution(self, edge_client):
        """Test that responses to pending requests are resolved."""
        # Create a future and add it to pending requests
        future = asyncio.Future()
        edge_client._pending_requests["test-request-id"] = future

        # Create a response
        response = pb2.EdgeMessage(
            request_id="test-request-id",
            registration_response=pb2.PeerRegistrationResponse(
                peer_name="test-peer-id",
                edge_name="test-edge",
                success=True
            )
        )

        # Process the response
        await edge_client._process_edge_message(response)

        # Verify that the future was completed with the response
        assert future.done()
        assert await future == response
        assert "test-request-id" not in edge_client._pending_requests

    @pytest.mark.asyncio
    async def test_handler_file_delete_request(self, edge_client):
        """Test handling a file delete request."""
        # Set up edge_client
        edge_client._stream = mock.AsyncMock()

        # Create a delete request
        request = pb2.FileDeleteRequest(
            catalog_uuids=["test-catalog-id-1", "test-catalog-id-2"]
        )

        # Call the handler
        await edge_client.handle_file_delete_request(request, "test-request-id")

        # Verify
        assert edge_client._stream.write.call_count == 2  # One response per catalog ID

        # Get the first response message
        response1 = edge_client._stream.write.call_args_list[0][0][0]
        assert response1.request_id == "test-request-id"
        assert response1.HasField("file_delete_response")
        assert response1.file_delete_response.catalog_uuid == "test-catalog-id-1"
        assert response1.file_delete_response.success is True

        # Get the second response message
        response2 = edge_client._stream.write.call_args_list[1][0][0]
        assert response2.request_id == "test-request-id"
        assert response2.HasField("file_delete_response")
        assert response2.file_delete_response.catalog_uuid == "test-catalog-id-2"
        assert response2.file_delete_response.success is True

    @pytest.mark.asyncio
    async def test_handle_file_hash_request(self, edge_client):
        """Test handling a file hash request."""
        # Set up edge_client
        edge_client._stream = mock.AsyncMock()

        # Create a hash request
        request = pb2.FileHashRequest(
            catalog_uuid="test-catalog-id",
            hash_types=["md5", "sha1"]
        )

        # Call the handler
        await edge_client.handle_file_hash_request(request, "test-request-id")

        # Verify
        assert edge_client._stream.write.call_count == 1

        # Get the response message
        response = edge_client._stream.write.call_args[0][0]
        assert response.request_id == "test-request-id"
        assert response.HasField("file_hash_response")
        assert response.file_hash_response.catalog_uuid == "test-catalog-id"
        assert len(response.file_hash_response.hashes) == 2
        assert "md5" in response.file_hash_response.hashes
        assert "sha1" in response.file_hash_response.hashes

    @pytest.mark.asyncio
    async def test_handle_screenshot_capture_request(self, edge_client):
        """Test handling a screenshot capture request."""
        # Set up edge_client
        edge_client._stream = mock.AsyncMock()

        # Create a screenshot request
        request = pb2.ScreenshotCaptureRequest(
            catalog_uuid="test-catalog-id",
            quantity=3,
            upload_token="test-token",
            upload_endpoint="/test/endpoint"
        )

        # Mock the database service
        with mock.patch("giggityflix_peer.services.db_service.db_service") as mock_db_service, \
                mock.patch(
                    "giggityflix_peer.services.screenshot_service.screenshot_service") as mock_screenshot_service:
            # Configure mocks
            # Mock media file
            media_file = mock.MagicMock()
            mock_db_service.get_media_file_by_catalog_id.return_value = media_file

            # Mock screenshots
            screenshots = [mock.MagicMock(), mock.MagicMock(), mock.MagicMock()]
            mock_screenshot_service.capture_screenshots.return_value = screenshots
            mock_screenshot_service.upload_screenshots.return_value = True

            # Call the handler
            await edge_client.handle_screenshot_capture_request(request, "test-request-id")

            # Verify
            mock_db_service.get_media_file_by_catalog_id.assert_called_once_with("test-catalog-id")
            mock_screenshot_service.capture_screenshots.assert_called_once_with(media_file, 3)
            mock_screenshot_service.upload_screenshots.assert_called_once_with(
                screenshots, "/test/endpoint", "test-token"
            )

            # Check the response
            assert edge_client._stream.write.call_count == 1
            response = edge_client._stream.write.call_args[0][0]
            assert response.request_id == "test-request-id"
            assert response.HasField("screenshot_capture_response")
            assert response.screenshot_capture_response.catalog_uuid == "test-catalog-id"
            assert response.screenshot_capture_response.HasField("screenshot")
