import asyncio
import logging
import uuid
from typing import Dict, List

import grpc
from giggityflix_grpc_peer import peer_edge_pb2 as pb2, peer_edge_pb2_grpc as pb2_grpc

from giggityflix_peer.config import config
from giggityflix_peer.models.media import MediaFile

logger = logging.getLogger(__name__)


class EdgeClient:
    """Client for communicating with the Edge Service."""

    def __init__(self, peer_id: str):
        """Initialize the Edge client."""
        self.peer_id = peer_id
        self.edge_address = config.grpc.edge_address
        self.reconnect_interval = config.grpc.reconnect_interval_sec
        self.max_reconnect_attempts = config.grpc.max_reconnect_attempts
        self.heartbeat_interval = config.grpc.heartbeat_interval_sec
        self.timeout = config.grpc.timeout_sec

        self._connected = False
        self._channel = None
        self._stub = None
        self._stream = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._stop_event = asyncio.Event()
        self._receive_task = None
        self._heartbeat_task = None

    async def connect(self) -> bool:
        """Connect to the Edge Service."""
        logger.info(f"Connecting to Edge Service at {self.edge_address}")

        # Create the gRPC channel
        if config.grpc.use_tls:
            if not config.grpc.cert_path:
                logger.error("TLS is enabled but no certificate path provided")
                return False

            with open(config.grpc.cert_path, 'rb') as f:
                creds = grpc.ssl_channel_credentials(f.read())
            self._channel = grpc.aio.secure_channel(self.edge_address, creds)
        else:
            self._channel = grpc.aio.insecure_channel(self.edge_address)

        # Create the stub
        self._stub = pb2_grpc.PeerEdgeServiceStub(self._channel)

        # Start the stream
        try:
            self._stream = self._stub.message()

            # Start the receive task
            self._receive_task = asyncio.create_task(self._receive_messages())

            # Register with the Edge Service
            success = await self._register()
            if not success:
                logger.error("Failed to register with Edge Service")
                await self.disconnect()
                return False

            # Start the heartbeat task
            self._heartbeat_task = asyncio.create_task(self._send_heartbeats())

            self._connected = True
            logger.info("Connected to Edge Service")
            return True

        except Exception as e:
            logger.error(f"Error connecting to Edge Service: {e}")
            await self.disconnect()
            return False

    async def disconnect(self) -> None:
        """Disconnect from the Edge Service."""
        logger.info("Disconnecting from Edge Service")

        # Signal tasks to stop
        self._stop_event.set()

        # Cancel tasks
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()

        # Close the stream
        if self._stream:
            await self._stream.cancel()
            self._stream = None

        # Close the channel
        if self._channel:
            await self._channel.close()
            self._channel = None

        # Fail all pending requests
        for request_id, future in self._pending_requests.items():
            if not future.done():
                future.set_exception(Exception("Connection closed"))

        self._pending_requests.clear()
        self._connected = False
        logger.info("Disconnected from Edge Service")

    async def reconnect(self) -> bool:
        """Reconnect to the Edge Service."""
        logger.info("Attempting to reconnect to Edge Service")

        # Disconnect if already connected
        if self._connected:
            await self.disconnect()

        # Try to connect with retries
        for attempt in range(1, self.max_reconnect_attempts + 1):
            if await self.connect():
                return True

            logger.info(
                f"Reconnect attempt {attempt}/{self.max_reconnect_attempts} failed, retrying in {self.reconnect_interval}s")
            await asyncio.sleep(self.reconnect_interval)

        logger.error("Failed to reconnect to Edge Service after maximum attempts")
        return False

    async def update_catalog(self, media_files: List[MediaFile]) -> bool:
        """Update the catalog with the Edge Service."""
        if not self._connected:
            logger.error("Not connected to Edge Service")
            return False

        try:
            # Extract the catalog UUIDs from the media files
            catalog_uuids = [str(mf.catalog_id) for mf in media_files if mf.catalog_id]

            # Create the batch file offer request
            file_items = []
            for media_file in media_files:
                if not media_file.luid or not media_file.relative_path:
                    continue

                file_item = pb2.FileOfferItem(
                    peer_luid=media_file.luid,
                    relative_path=media_file.relative_path,
                    size_bytes=media_file.size_bytes
                )

                file_items.append(file_item)

            if not file_items:
                logger.warning("No valid media files to offer")
                return False

            batch_offer = pb2.BatchFileOfferRequest(
                files=file_items,
                category_type="media"  # This could be more specific based on media types
            )

            # Create the request ID
            request_id = str(uuid.uuid4())

            # Create the peer message
            peer_message = pb2.PeerMessage(
                request_id=request_id,
                batch_file_offer_request=batch_offer
            )

            # Create a future for the response
            response_future = asyncio.Future()
            self._pending_requests[request_id] = response_future

            # Send the message
            await self._stream.write(peer_message)

            # Wait for the response with timeout
            try:
                response = await asyncio.wait_for(response_future, timeout=self.timeout)

                # Process the response
                if not response.HasField('batch_file_offer_response'):
                    logger.error("Unexpected response type")
                    return False

                # Map the catalog IDs assigned by the server to our local files
                for file_result in response.batch_file_offer_response.files:
                    # Find the matching media file by peer_luid
                    for media_file in media_files:
                        if media_file.luid == file_result.peer_luid:
                            media_file.catalog_id = file_result.catalog_uuid
                            break

                logger.info(f"Catalog updated successfully with {len(response.batch_file_offer_response.files)} files")
                return True

            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for batch file offer response after {self.timeout}s")
                del self._pending_requests[request_id]
                return False

        except Exception as e:
            logger.error(f"Error updating catalog: {e}")
            return False

    async def handle_file_delete_request(self, request: pb2.FileDeleteRequest, request_id: str) -> None:
        """Handle a file delete request from the Edge Service."""
        logger.info(f"Received file delete request for {len(request.catalog_uuids)} files")

        # Process each catalog UUID
        for catalog_uuid in request.catalog_uuids:
            try:
                # This would typically involve finding the file in the database and deleting it
                # For now, we'll just log it
                logger.info(f"Processing delete request for catalog ID {catalog_uuid}")

                # TODO: Implement file deletion logic

                # Send success response
                response = pb2.PeerMessage(
                    request_id=request_id,
                    file_delete_response=pb2.FileDeleteResponse(
                        catalog_uuid=catalog_uuid,
                        success=True
                    )
                )

                await self._stream.write(response)

            except Exception as e:
                logger.error(f"Error processing delete request for {catalog_uuid}: {e}")

                # Send error response
                response = pb2.PeerMessage(
                    request_id=request_id,
                    file_delete_response=pb2.FileDeleteResponse(
                        catalog_uuid=catalog_uuid,
                        success=False,
                        error_message=str(e)
                    )
                )

                await self._stream.write(response)

    async def handle_file_hash_request(self, request: pb2.FileHashRequest, request_id: str) -> None:
        """Handle a file hash request from the Edge Service."""
        logger.info(f"Received file hash request for {request.catalog_uuid}")

        try:
            # This would typically involve finding the file in the database and getting its hashes
            # For now, we'll just send a placeholder response
            logger.info(f"Processing hash request for catalog ID {request.catalog_uuid}")

            # TODO: Implement hash calculation logic

            # Send success response with placeholder hashes
            hashes = {}
            for algorithm in request.hash_types:
                hashes[algorithm] = f"placeholder-hash-for-{algorithm}"

            response = pb2.PeerMessage(
                request_id=request_id,
                file_hash_response=pb2.FileHashResponse(
                    catalog_uuid=request.catalog_uuid,
                    hashes=hashes
                )
            )

            await self._stream.write(response)

        except Exception as e:
            logger.error(f"Error processing hash request for {request.catalog_uuid}: {e}")

            # Send error response
            response = pb2.PeerMessage(
                request_id=request_id,
                file_hash_response=pb2.FileHashResponse(
                    catalog_uuid=request.catalog_uuid,
                    error_message=str(e)
                )
            )

            await self._stream.write(response)

    async def handle_file_remap_request(self, request: pb2.FileRemapRequest, request_id: str) -> None:
        """Handle a file remap request from the Edge Service."""
        logger.info(f"Received file remap request: {request.old_catalog_uuid} -> {request.new_catalog_uuid}")

        # This would typically involve updating the catalog ID in the database
        # For now, we'll just log it
        logger.info(f"Processing remap request for catalog ID {request.old_catalog_uuid} -> {request.new_catalog_uuid}")

        # TODO: Implement file remapping logic

    async def handle_screenshot_capture_request(self, request: pb2.ScreenshotCaptureRequest, request_id: str) -> None:
        """Handle a screenshot capture request from the Edge Service."""
        from giggityflix_peer.services.db_service import db_service
        from giggityflix_peer.services.screenshot_service import screenshot_service

        logger.info(f"Received screenshot capture request for {request.catalog_uuid}")

        try:
            # Get the quantity from the request
            quantity = max(1, request.quantity)

            # Find the media file by catalog ID
            media_file = await db_service.get_media_file_by_catalog_id(request.catalog_uuid)

            if not media_file:
                logger.error(f"Media file not found for catalog ID {request.catalog_uuid}")

                # Send error response
                response = pb2.PeerMessage(
                    request_id=request_id,
                    screenshot_capture_response=pb2.ScreenshotCaptureResponse(
                        catalog_uuid=request.catalog_uuid,
                        error_message="Media file not found"
                    )
                )

                await self._stream.write(response)
                return

            # Capture screenshots
            screenshots = await screenshot_service.capture_screenshots(media_file, quantity)

            if not screenshots:
                logger.error(f"Failed to capture screenshots for {request.catalog_uuid}")

                # Send error response
                response = pb2.PeerMessage(
                    request_id=request_id,
                    screenshot_capture_response=pb2.ScreenshotCaptureResponse(
                        catalog_uuid=request.catalog_uuid,
                        error_message="Failed to capture screenshots"
                    )
                )

                await self._stream.write(response)
                return

            # Upload screenshots
            success = await screenshot_service.upload_screenshots(
                screenshots,
                request.upload_endpoint,
                request.upload_token
            )

            if not success:
                logger.error(f"Failed to upload screenshots for {request.catalog_uuid}")

                # Send error response
                response = pb2.PeerMessage(
                    request_id=request_id,
                    screenshot_capture_response=pb2.ScreenshotCaptureResponse(
                        catalog_uuid=request.catalog_uuid,
                        error_message="Failed to upload screenshots"
                    )
                )

                await self._stream.write(response)
                return

            # Send success response
            logger.info(f"Successfully captured and uploaded {len(screenshots)} screenshots for {request.catalog_uuid}")

            # We don't actually send the screenshot data in the response anymore
            # since it's uploaded directly, but we send a success response
            response = pb2.PeerMessage(
                request_id=request_id,
                screenshot_capture_response=pb2.ScreenshotCaptureResponse(
                    catalog_uuid=request.catalog_uuid,
                    screenshot=pb2.ScreenshotData(
                        frame_number_in_video=0,
                        screenshot=b""  # Empty since we uploaded directly
                    )
                )
            )

            await self._stream.write(response)

        except Exception as e:
            logger.error(f"Error processing screenshot request for {request.catalog_uuid}: {e}", exc_info=True)

            # Send error response
            response = pb2.PeerMessage(
                request_id=request_id,
                screenshot_capture_response=pb2.ScreenshotCaptureResponse(
                    catalog_uuid=request.catalog_uuid,
                    error_message=str(e)
                )
            )

            await self._stream.write(response)

    async def _register(self) -> bool:
        """Register with the Edge Service."""
        logger.info(f"Registering with Edge Service as peer {self.peer_id}")

        try:
            # Create the registration request
            request_id = str(uuid.uuid4())

            registration_request = pb2.PeerRegistrationRequest(
                peer_name=self.peer_id,
                catalog_uuids=[]  # Empty for initial registration
            )

            # Create the peer message
            peer_message = pb2.PeerMessage(
                request_id=request_id,
                registration_request=registration_request
            )

            # Create a future for the response
            response_future = asyncio.Future()
            self._pending_requests[request_id] = response_future

            # Send the message
            await self._stream.write(peer_message)

            # Wait for the response with timeout
            try:
                response = await asyncio.wait_for(response_future, timeout=self.timeout)

                # Process the response
                if not response.HasField('registration_response'):
                    logger.error("Unexpected response type")
                    return False

                if not response.registration_response.success:
                    logger.error("Registration failed")
                    return False

                logger.info(f"Registered successfully with edge {response.registration_response.edge_name}")
                return True

            except asyncio.TimeoutError:
                logger.error(f"Timeout waiting for registration response after {self.timeout}s")
                del self._pending_requests[request_id]
                return False

        except Exception as e:
            logger.error(f"Error registering with Edge Service: {e}")
            return False

    async def _receive_messages(self) -> None:
        """Receive messages from the Edge Service."""
        try:
            async for edge_message in self._stream:
                # Process the message
                await self._process_edge_message(edge_message)

        except asyncio.CancelledError:
            logger.info("Message receiving task cancelled")

        except Exception as e:
            logger.error(f"Error receiving messages: {e}")

            # If we're still connected, try to reconnect
            if self._connected:
                asyncio.create_task(self.reconnect())

    async def _process_edge_message(self, message: pb2.EdgeMessage) -> None:
        """Process a message from the Edge Service."""
        request_id = message.request_id

        # Check if this is a response to a pending request
        if request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(message)
            return

        # Otherwise, this is a new request from the Edge Service
        # Handle based on the message type
        if message.HasField('file_delete_request'):
            await self.handle_file_delete_request(message.file_delete_request, request_id)

        elif message.HasField('file_hash_request'):
            await self.handle_file_hash_request(message.file_hash_request, request_id)

        elif message.HasField('file_remap_request'):
            await self.handle_file_remap_request(message.file_remap_request, request_id)

        elif message.HasField('screenshot_capture_request'):
            await self.handle_screenshot_capture_request(message.screenshot_capture_request, request_id)

        else:
            logger.warning(f"Received unknown message type: {message}")

    async def _send_heartbeats(self) -> None:
        """Send periodic heartbeats to the Edge Service."""
        while not self._stop_event.is_set():
            try:
                # Wait for the heartbeat interval
                await asyncio.sleep(self.heartbeat_interval)

                # Send a heartbeat by updating the catalog with an empty list
                # In a real implementation, we would periodically send the full catalog
                # But for now, just use an empty list as a heartbeat
                if self._connected:
                    logger.debug("Sending heartbeat")
                    await self.update_catalog([])

            except asyncio.CancelledError:
                logger.info("Heartbeat task cancelled")
                break

            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
