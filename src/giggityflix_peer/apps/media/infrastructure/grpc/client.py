"""gRPC client for media peer communication."""
import asyncio
import logging
import uuid
from typing import List, Optional, Tuple

import grpc
from django.conf import settings
from giggityflix_grpc_peer import (
    PeerEdgeServiceStub, EdgeMessage, PeerMessage, PeerWebRTCMessage, EdgeWebRTCMessage,
    catalog, webrtc
)

from ...domain.models import Media
from .handlers import MediaGrpcHandlers

logger = logging.getLogger(__name__)


class MediaGrpcClient:
    """gRPC client for edge service communication."""

    def __init__(self, peer_id: str):
        self.peer_id = peer_id
        self.handlers = MediaGrpcHandlers()
        self._channel = None
        self._stub = None
        self._stream = None
        self._connected = False
        self._pending_requests = {}
        self._receive_task = None
        self._stop_event = asyncio.Event()

    async def connect(self) -> bool:
        """Connect to edge service."""
        if self._connected:
            return True

        try:
            edge_address = getattr(settings, 'EDGE_GRPC_ADDRESS', 'localhost:50051')
            use_tls = getattr(settings, 'GRPC_USE_TLS', False)
            
            logger.info(f"Connecting to edge service at {edge_address}")

            if use_tls:
                cert_path = getattr(settings, 'GRPC_CERT_PATH', None)
                if cert_path:
                    with open(cert_path, 'rb') as f:
                        cert_data = f.read()
                    self._channel = grpc.aio.secure_channel(edge_address, grpc.ssl_channel_credentials(cert_data))
                else:
                    logger.warning("TLS requested but no cert path provided, using insecure channel")
                    self._channel = grpc.aio.insecure_channel(edge_address)
            else:
                self._channel = grpc.aio.insecure_channel(edge_address)

            self._stub = PeerEdgeServiceStub(self._channel)
            metadata = (('peer_id', self.peer_id),)
            self._stream = self._stub.AsyncOperations(metadata=metadata)
            
            self._receive_task = asyncio.create_task(self._receive_messages())
            await self._send_registration()
            
            self._connected = True
            logger.info("Connected to edge service")
            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            await self._cleanup()
            return False

    async def disconnect(self) -> None:
        """Disconnect from edge service."""
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        self._connected = False
        
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            self._receive_task = None

        if self._stream:
            try:
                await self._stream.done_writing()
            except Exception:
                pass
            self._stream = None

        if self._channel:
            try:
                await self._channel.close()
            except Exception:
                pass
            self._channel = None

        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(ConnectionError("Disconnected"))
        self._pending_requests.clear()

    async def _send_registration(self) -> bool:
        """Send initial registration message."""
        announcement = catalog.CatalogAnnouncementResponse(catalog_ids=[])
        message = PeerMessage(
            request_id=str(uuid.uuid4()),
            catalog_announcement=announcement
        )
        response = await self.send_message(message)
        return response is not None

    async def _receive_messages(self) -> None:
        """Receive and process messages from edge service."""
        try:
            async for message in self._stream:
                asyncio.create_task(self._process_message(message))
        except asyncio.CancelledError:
            logger.debug("Message receiver cancelled")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            if self._connected:
                await self._cleanup()

    async def _process_message(self, message: EdgeMessage) -> None:
        """Process message from edge service."""
        try:
            request_id = message.request_id

            if request_id in self._pending_requests:
                future = self._pending_requests.pop(request_id)
                if not future.done():
                    future.set_result(message)
                return

            response = await self.handlers.handle_message(message)
            if response:
                await self.send_message(response)

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def send_message(self, message: PeerMessage) -> Optional[EdgeMessage]:
        """Send message to edge service."""
        if not self._connected or not self._stream:
            logger.error("Not connected to edge service")
            return None

        try:
            request_id = message.request_id
            response_future = asyncio.Future()
            self._pending_requests[request_id] = response_future

            await self._stream.write(message)
            
            timeout = getattr(settings, 'GRPC_TIMEOUT_SEC', 30)
            try:
                return await asyncio.wait_for(response_future, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Response timeout for request {request_id}")
                return None
            finally:
                self._pending_requests.pop(request_id, None)

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None

    async def announce_catalog(self, catalog_ids: List[str]) -> bool:
        """Announce catalog IDs to edge service."""
        if not catalog_ids:
            return False

        try:
            announcement = catalog.CatalogAnnouncementResponse(catalog_ids=catalog_ids)
            message = PeerMessage(
                request_id=str(uuid.uuid4()),
                catalog_announcement=announcement
            )
            response = await self.send_message(message)
            return response is not None

        except Exception as e:
            logger.error(f"Error announcing catalog: {e}")
            return False

    async def announce_files(self, media_list: List[Media]) -> List[str]:
        """Announce files to edge service to get catalog IDs."""
        if not media_list:
            return []

        try:
            file_infos = []
            for media in media_list:
                if media.relative_path and media.status.value != 'deleted':
                    file_info = catalog.FileInfo(
                        relative_path=media.relative_path,
                        size_bytes=media.size_bytes
                    )
                    file_infos.append(file_info)

            if not file_infos:
                return []

            request = catalog.FileOfferRequest(files=file_infos)
            message = PeerMessage(
                request_id=str(uuid.uuid4()),
                batch_file_offer=request
            )

            response = await self.send_message(message)
            catalog_ids = []
            
            if response and response.HasField('batch_file_offer_response'):
                for file_info in response.batch_file_offer_response.files:
                    catalog_ids.append(file_info.catalog_id)

            return catalog_ids

        except Exception as e:
            logger.error(f"Error announcing files: {e}")
            return []

    async def create_stream_session(self, catalog_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Create WebRTC streaming session."""
        try:
            session_id = str(uuid.uuid4())
            
            request = webrtc.StreamSessionRequest(
                catalog_id=catalog_id,
                session_id=session_id
            )

            message = EdgeWebRTCMessage(
                request_id=str(uuid.uuid4()),
                stream_session_request=request
            )

            response = await self.send_webrtc_message(message)

            if response and response.HasField('stream_session_response'):
                if response.stream_session_response.success:
                    return session_id, None
                else:
                    logger.warning(f"Stream session request failed: {response.stream_session_response.error}")
                    return None, None
            elif response and response.HasField('sdp_offer'):
                return session_id, response.sdp_offer.sdp
            else:
                return None, None

        except Exception as e:
            logger.error(f"Error creating stream session: {e}")
            return None, None

    async def send_webrtc_message(self, message: EdgeWebRTCMessage) -> Optional[PeerWebRTCMessage]:
        """Send WebRTC message to edge service."""
        if not self._connected:
            return None

        try:
            timeout = getattr(settings, 'GRPC_TIMEOUT_SEC', 30)
            return await self._stub.WebRTCOperations(
                message,
                metadata=(('peer_id', self.peer_id),),
                timeout=timeout
            )
        except Exception as e:
            logger.error(f"Error sending WebRTC message: {e}")
            return None
