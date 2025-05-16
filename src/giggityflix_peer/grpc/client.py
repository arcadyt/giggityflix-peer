import asyncio
import logging
import uuid
from typing import Dict, List, Optional

import grpc

from giggityflix_grpc_peer import (
    PeerEdgeServiceStub, EdgeMessage, PeerMessage,
    catalog, file_operations
)
from .handlers import EdgeMessageHandler

logger = logging.getLogger(__name__)


class EdgeClient:
    """Client for edge service communication."""

    def __init__(
            self,
            peer_id: str,
            edge_address: str,
            message_handler: EdgeMessageHandler,
            use_tls: bool = False,
            cert_path: Optional[str] = None
    ):
        self.peer_id = peer_id
        self.edge_address = edge_address
        self.use_tls = use_tls
        self.cert_path = cert_path
        self.handler = message_handler
        self._channel = None
        self._stub = None
        self._stream = None
        self._connected = False
        self._pending_requests = {}
        self._receive_task = None

    async def connect(self) -> bool:
        """Connects to edge service."""
        try:
            # Create channel
            if self.use_tls:
                with open(self.cert_path, 'rb') as f:
                    cert_data = f.read()
                self._channel = grpc.aio.secure_channel(
                    self.edge_address,
                    grpc.ssl_channel_credentials(cert_data)
                )
            else:
                self._channel = grpc.aio.insecure_channel(self.edge_address)

            # Create stub
            self._stub = PeerEdgeServiceStub(self._channel)

            # Add peer_id to metadata
            metadata = (('peer_id', self.peer_id),)

            # Start bidirectional stream
            self._stream = self._stub.AsyncOperations(metadata=metadata)

            # Start message receiver
            self._receive_task = asyncio.create_task(self._receive_messages())

            # Initial registration
            await self._send_registration()

            self._connected = True
            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            await self._cleanup()
            return False

    async def disconnect(self) -> None:
        """Disconnects from edge service."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Cleans up resources."""
        self._connected = False

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        if self._stream:
            await self._stream.done_writing()
            self._stream = None

        if self._channel:
            await self._channel.close()
            self._channel = None

        # Complete pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(ConnectionError("Disconnected"))
        self._pending_requests.clear()

    async def _send_registration(self) -> bool:
        """Sends registration message."""
        announcement = catalog.CatalogAnnouncementResponse(
            catalog_ids=[]  # Empty initially
        )

        message = PeerMessage(
            request_id=str(uuid.uuid4()),
            catalog_announcement=announcement
        )

        response = await self.send_message(message)
        return response is not None

    async def _receive_messages(self) -> None:
        """Receives messages from edge service."""
        try:
            async for message in self._stream:
                await self._process_message(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Stream error: {e}")
            if self._connected:
                # Attempt reconnect
                pass

    async def _process_message(self, message: EdgeMessage) -> None:
        """Processes message from edge service."""
        request_id = message.request_id

        # Check for pending request
        if request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(message)
            return

        # Handle message
        response = await self.handler.handle_message(message)
        if response:
            await self.send_message(response)

    async def send_message(self, message: PeerMessage) -> Optional[EdgeMessage]:
        """Sends message to edge service."""
        if not self._connected or not self._stream:
            logger.error("Not connected")
            return None

        try:
            # Create future for response
            request_id = message.request_id
            response_future = asyncio.Future()
            self._pending_requests[request_id] = response_future

            # Send message
            await self._stream.write(message)

            # Wait for response
            try:
                return await asyncio.wait_for(response_future, timeout=30)
            except asyncio.TimeoutError:
                logger.warning(f"Response timeout: {request_id}")
                return None
            finally:
                self._pending_requests.pop(request_id, None)

        except Exception as e:
            logger.error(f"Send error: {e}")
            return None

    # High-level API methods

    async def announce_files(self, file_infos: List[catalog.FileInfo]) -> Optional[List[catalog.CatalogedInfo]]:
        """Announces files to edge service."""
        request = catalog.FileOfferRequest(files=file_infos)

        message = PeerMessage(
            request_id=str(uuid.uuid4()),
            batch_file_offer=request
        )

        response = await self.send_message(message)

        if response and response.HasField('batch_file_offer_response'):
            return list(response.batch_file_offer_response.files)
        return None

    async def send_file_hash_response(self, catalog_id: str, hashes: Dict[str, str],
                                      request_id: str, success: bool = True) -> bool:
        """Sends file hash computation results."""
        response = file_operations.FileHashResponse(
            catalog_id=catalog_id,
            hashes=hashes,
            success=success
        )

        message = PeerMessage(
            request_id=request_id,
            file_hash_response=response
        )

        return await self.send_message(message) is not None

    async def send_file_delete_response(self, catalog_id: str, success: bool,
                                        request_id: str, error=None) -> bool:
        """Sends file deletion result."""
        response = file_operations.FileDeleteResponse(
            catalog_id=catalog_id,
            success=success
        )

        if error is not None:
            response.error = error

        message = PeerMessage(
            request_id=request_id,
            file_delete_response=response
        )

        return await self.send_message(message) is not None