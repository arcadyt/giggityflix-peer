import asyncio
import logging
import uuid
from typing import List, Optional, Tuple

import grpc
from giggityflix_grpc_peer import (
    PeerEdgeServiceStub, EdgeMessage, PeerMessage, PeerWebRTCMessage, EdgeWebRTCMessage,
    catalog, webrtc
)

from giggityflix_peer.models.media import MediaFile, MediaStatus
from giggityflix_peer.services.config_service import config_service
from .handlers import EdgeMessageHandler

logger = logging.getLogger(__name__)


class EdgeClient:
    """
    Client for edge service communication.
    
    This class is a wrapper around the gRPC client to the edge service. It manages
    connection, reconnection, message sending/receiving, and provides high-level
    API methods for communicating with the edge service.
    """

    def __init__(
            self,
            peer_id: str,
            message_handler: Optional[EdgeMessageHandler] = None
    ):
        """
        Initialize the edge client.
        
        Args:
            peer_id: Unique identifier for this peer
            message_handler: Handler for processing incoming messages
        """
        self.peer_id = peer_id
        self.handler = message_handler or EdgeMessageHandler()

        # Connection parameters (will be loaded from config)
        self._edge_address = None
        self._use_tls = None
        self._cert_path = None
        self._timeout = None
        self._heartbeat_interval = None
        self._max_reconnect_attempts = None
        self._reconnect_interval = None

        # Connection state
        self._channel = None
        self._stub = None
        self._stream = None
        self._connected = False
        self._pending_requests = {}  # request_id -> Future
        self._config_watch_task = None
        self._config_version = None

        # Tasks
        self._receive_task = None
        self._heartbeat_task = None
        self._reconnect_task = None
        self._stop_event = asyncio.Event()
        self._reconnect_attempts = 0

    async def start(self) -> bool:
        """
        Start the edge client and connect to the edge service.
        
        Returns:
            True if connected successfully, False otherwise
        """
        # Reset stop event
        self._stop_event.clear()

        # Load configuration
        await self._load_config()

        # Start config watcher
        self._config_watch_task = asyncio.create_task(self._watch_config())

        # Connect to edge service
        return await self.connect()

    async def stop(self) -> None:
        """Stop the edge client and disconnect from the edge service."""
        self._stop_event.set()

        # Cancel tasks
        if self._config_watch_task and not self._config_watch_task.done():
            self._config_watch_task.cancel()

        # Disconnect
        await self.disconnect()

    async def connect(self) -> bool:
        """
        Connect to the edge service.
        
        Returns:
            True if connected successfully, False otherwise
        """
        if self._connected:
            return True

        try:
            # Ensure config is loaded
            if not self._edge_address:
                await self._load_config()

            logger.info(f"Connecting to edge service at {self._edge_address}")

            # Create channel
            if self._use_tls and self._cert_path:
                try:
                    with open(self._cert_path, 'rb') as f:
                        cert_data = f.read()
                    self._channel = grpc.aio.secure_channel(
                        self._edge_address,
                        grpc.ssl_channel_credentials(cert_data)
                    )
                    logger.debug("Using TLS for edge connection")
                except FileNotFoundError:
                    logger.warning(f"TLS certificate not found at {self._cert_path}, using insecure channel")
                    self._channel = grpc.aio.insecure_channel(self._edge_address)
            else:
                logger.debug("Using insecure channel for edge connection")
                self._channel = grpc.aio.insecure_channel(self._edge_address)

            # Create stub
            self._stub = PeerEdgeServiceStub(self._channel)

            # Add peer_id to metadata
            metadata = (('peer_id', self.peer_id),)

            # Start bidirectional stream
            self._stream = self._stub.AsyncOperations(metadata=metadata)

            # Start message receiver
            self._receive_task = asyncio.create_task(self._receive_messages())

            # Start heartbeat task
            if self._heartbeat_interval > 0:
                self._heartbeat_task = asyncio.create_task(self._send_heartbeats())

            # Initial registration
            await self._send_registration()

            self._connected = True
            self._reconnect_attempts = 0
            logger.info(f"Connected to edge service at {self._edge_address}")
            return True

        except Exception as e:
            logger.error(f"Connection error: {e}")
            await self._cleanup(reconnect=True)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the edge service."""
        await self._cleanup(reconnect=False)

    async def _cleanup(self, reconnect: bool = False) -> None:
        """
        Clean up resources and optionally schedule reconnection.
        
        Args:
            reconnect: Whether to attempt reconnection
        """
        self._connected = False

        # Cancel tasks
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            self._receive_task = None

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        # Close stream
        if self._stream:
            try:
                await self._stream.done_writing()
            except Exception as e:
                logger.debug(f"Error closing stream: {e}")
            self._stream = None

        # Close channel
        if self._channel:
            try:
                await self._channel.close()
            except Exception as e:
                logger.debug(f"Error closing channel: {e}")
            self._channel = None

        # Complete pending requests
        for future in self._pending_requests.values():
            if not future.done():
                future.set_exception(ConnectionError("Disconnected"))
        self._pending_requests.clear()

        # Schedule reconnect if needed
        if reconnect and not self._stop_event.is_set():
            if self._reconnect_task and not self._reconnect_task.done():
                self._reconnect_task.cancel()

            if self._reconnect_attempts < self._max_reconnect_attempts:
                self._reconnect_attempts += 1
                backoff = min(self._reconnect_interval * (2 ** (self._reconnect_attempts - 1)), 300)  # Max 5 minutes
                logger.info(
                    f"Scheduling reconnect in {backoff} seconds (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts})")
                self._reconnect_task = asyncio.create_task(self._delayed_reconnect(backoff))
            else:
                logger.error(f"Max reconnect attempts ({self._max_reconnect_attempts}) reached, giving up")

    async def _delayed_reconnect(self, delay: float) -> None:
        """
        Wait for the specified delay and attempt reconnection.
        
        Args:
            delay: Time to wait in seconds
        """
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            # Timeout expired, attempt reconnection
            if not self._stop_event.is_set():
                await self.connect()

    async def _load_config(self) -> None:
        """Load configuration from config service."""
        try:
            # Load configuration values
            self._edge_address = await config_service.get("edge_address", "localhost:50051")
            self._use_tls = await config_service.get("use_tls", False)
            self._cert_path = await config_service.get("cert_path", None)
            self._timeout = await config_service.get("grpc_timeout_sec", 30)
            self._heartbeat_interval = await config_service.get("heartbeat_interval_sec", 30)
            self._max_reconnect_attempts = await config_service.get("max_reconnect_attempts", 5)
            self._reconnect_interval = await config_service.get("reconnect_interval_sec", 10)

            # Get config version for change detection
            settings = await config_service.get_all()
            self._config_version = hash(frozenset((k, str(v["value"])) for k, v in settings.items()
                                                  if k in ["edge_address", "use_tls", "cert_path"]))

            logger.debug(f"Loaded configuration: edge_address={self._edge_address}, use_tls={self._use_tls}")

        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            # Use defaults if config service fails
            self._edge_address = "localhost:50051"
            self._use_tls = False
            self._cert_path = None
            self._timeout = 30
            self._heartbeat_interval = 30
            self._max_reconnect_attempts = 5
            self._reconnect_interval = 10

    async def _watch_config(self) -> None:
        """Watch for configuration changes."""
        while not self._stop_event.is_set():
            try:
                # Check for config changes
                settings = await config_service.get_all()
                new_config_version = hash(frozenset((k, str(v["value"])) for k, v in settings.items()
                                                    if k in ["edge_address", "use_tls", "cert_path"]))

                if new_config_version != self._config_version:
                    logger.info("Connection configuration changed, reconnecting")
                    self._config_version = new_config_version
                    await self._load_config()

                    # Reconnect if already connected
                    if self._connected:
                        await self._cleanup(reconnect=True)

                # Wait before checking again
                await asyncio.sleep(30)  # Check every 30 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error watching configuration: {e}")
                await asyncio.sleep(60)  # Longer delay on error

    async def _send_registration(self) -> bool:
        """
        Send initial registration message.
        
        Returns:
            True if successful, False otherwise
        """
        # Create empty catalog announcement
        announcement = catalog.CatalogAnnouncementResponse(
            catalog_ids=[]  # Empty initially, will be updated with actual catalog IDs
        )

        message = PeerMessage(
            request_id=str(uuid.uuid4()),
            catalog_announcement=announcement
        )

        response = await self.send_message(message)
        return response is not None

    async def _send_heartbeats(self) -> None:
        """Periodically send heartbeat messages to keep connection alive."""
        while not self._stop_event.is_set() and self._connected:
            try:
                # Send heartbeat if connected
                if self._connected:
                    # Create catalog announcement with empty list
                    announcement = catalog.CatalogAnnouncementResponse(
                        catalog_ids=[]
                    )

                    message = PeerMessage(
                        request_id=str(uuid.uuid4()),
                        catalog_announcement=announcement
                    )

                    await self.send_message(message)

                # Wait for next heartbeat
                await asyncio.sleep(self._heartbeat_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
                # If heartbeat fails, we might be disconnected
                if self._connected:
                    await self._cleanup(reconnect=True)
                break

    async def _receive_messages(self) -> None:
        """Receive and process messages from the edge service."""
        try:
            async for message in self._stream:
                asyncio.create_task(self._process_message(message))
        except asyncio.CancelledError:
            logger.debug("Message receiver cancelled")
        except Exception as e:
            logger.error(f"Stream error: {e}")
            if self._connected:
                await self._cleanup(reconnect=True)

    async def _process_message(self, message: EdgeMessage) -> None:
        """
        Process a message from the edge service.
        
        Args:
            message: The message to process
        """
        try:
            request_id = message.request_id

            # Check for pending request
            if request_id in self._pending_requests:
                future = self._pending_requests.pop(request_id)
                if not future.done():
                    future.set_result(message)
                return

            # Handle message with the message handler
            logger.debug(f"Processing edge message: {message.WhichOneof('payload')}")
            response = await self.handler.handle_message(message)
            if response:
                await self.send_message(response)

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def send_message(self, message: PeerMessage) -> Optional[EdgeMessage]:
        """
        Send a message to the edge service.
        
        Args:
            message: The message to send
            
        Returns:
            Response message or None if no response or error
        """
        if not self._connected or not self._stream:
            logger.error("Not connected to edge service")
            return None

        try:
            # Create future for response
            request_id = message.request_id
            response_future = asyncio.Future()
            self._pending_requests[request_id] = response_future

            # Send message
            await self._stream.write(message)
            logger.debug(f"Sent message: {message.WhichOneof('payload')}")

            # Wait for response
            try:
                return await asyncio.wait_for(response_future, timeout=self._timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Response timeout for request {request_id}")
                return None
            finally:
                self._pending_requests.pop(request_id, None)

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None

    async def send_webrtc_message(self, message: EdgeWebRTCMessage) -> Optional[PeerWebRTCMessage]:
        """
        Send a WebRTC message to the edge service.
        
        Args:
            message: The WebRTC message to send
            
        Returns:
            WebRTC response message or None if error
        """
        if not self._connected:
            logger.error("Not connected to edge service")
            return None

        try:
            # Send unary RPC request
            return await self._stub.WebRTCOperations(
                message,
                metadata=(('peer_id', self.peer_id),),
                timeout=self._timeout
            )
        except Exception as e:
            logger.error(f"Error sending WebRTC message: {e}")
            return None

    # High-level API methods

    async def announce_catalog(self, catalog_ids: List[str]) -> bool:
        """
        Announce catalog IDs to the edge service.
        
        Args:
            catalog_ids: List of catalog IDs to announce
            
        Returns:
            True if successful, False otherwise
        """
        if not catalog_ids:
            logger.warning("No catalog IDs to announce")
            return False

        try:
            announcement = catalog.CatalogAnnouncementResponse(
                catalog_ids=catalog_ids
            )

            message = PeerMessage(
                request_id=str(uuid.uuid4()),
                catalog_announcement=announcement
            )

            response = await self.send_message(message)
            return response is not None

        except Exception as e:
            logger.error(f"Error announcing catalog: {e}")
            return False

    async def announce_files(self, media_files: List[MediaFile]) -> List[str]:
        """
        Announce files to the edge service to get catalog IDs.
        
        Args:
            media_files: List of media files to announce
            
        Returns:
            List of assigned catalog IDs
        """
        if not media_files:
            logger.warning("No files to announce")
            return []

        try:
            # Convert to FileInfo objects
            file_infos = []
            for media_file in media_files:
                if media_file.status != MediaStatus.DELETED and media_file.relative_path:
                    file_info = catalog.FileInfo(
                        relative_path=media_file.relative_path,
                        size_bytes=media_file.size_bytes
                    )
                    file_infos.append(file_info)

            if not file_infos:
                logger.warning("No valid files to announce")
                return []

            # Create batch file offer
            request = catalog.FileOfferRequest(files=file_infos)
            message = PeerMessage(
                request_id=str(uuid.uuid4()),
                batch_file_offer=request
            )

            # Send and wait for response
            response = await self.send_message(message)

            # Process response
            catalog_ids = []
            if response and response.HasField('batch_file_offer_response'):
                for file_info in response.batch_file_offer_response.files:
                    catalog_ids.append(file_info.catalog_id)

                    # Find corresponding media file and update catalog ID
                    for media_file in media_files:
                        if media_file.relative_path == file_info.relative_path:
                            media_file.catalog_id = file_info.catalog_id

            return catalog_ids

        except Exception as e:
            logger.error(f"Error announcing files: {e}")
            return []

    async def create_stream_session(self, catalog_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Create a WebRTC streaming session for a media file.
        
        Args:
            catalog_id: Catalog ID of the media file
            
        Returns:
            Tuple of (session_id, sdp_offer) or (None, None) if error
        """
        try:
            # Generate session ID
            session_id = str(uuid.uuid4())

            # Create stream session request
            request = webrtc.StreamSessionRequest(
                catalog_id=catalog_id,
                session_id=session_id
            )

            # Create WebRTC message
            message = EdgeWebRTCMessage(
                request_id=str(uuid.uuid4()),
                stream_session_request=request
            )

            # Send message
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
                logger.warning("Invalid stream session response")
                return None, None

        except Exception as e:
            logger.error(f"Error creating stream session: {e}")
            return None, None

    async def send_sdp_answer(self, session_id: str, sdp: str) -> bool:
        """
        Send SDP answer for a WebRTC session.
        
        Args:
            session_id: ID of the streaming session
            sdp: SDP answer
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create SDP answer
            answer = webrtc.SDPAnswer(
                session_id=session_id,
                sdp=sdp
            )

            # Create WebRTC message
            message = EdgeWebRTCMessage(
                request_id=str(uuid.uuid4()),
                sdp_answer=answer
            )

            # Send message
            response = await self.send_webrtc_message(message)
            return response is not None

        except Exception as e:
            logger.error(f"Error sending SDP answer: {e}")
            return False

    async def send_ice_candidate(self, session_id: str, candidate: str,
                                 sdp_mid: str, sdp_mline_index: int) -> bool:
        """
        Send ICE candidate for a WebRTC session.
        
        Args:
            session_id: ID of the streaming session
            candidate: ICE candidate string
            sdp_mid: SDP mid attribute
            sdp_mline_index: SDP M-line index
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create ICE candidate
            ice = webrtc.ICECandidate(
                session_id=session_id,
                candidate=candidate,
                sdp_mid=sdp_mid,
                sdp_m_line_index=sdp_mline_index
            )

            # Create WebRTC message
            message = EdgeWebRTCMessage(
                request_id=str(uuid.uuid4()),
                ice_candidate=ice
            )

            # Send message
            response = await self.send_webrtc_message(message)
            return response is not None

        except Exception as e:
            logger.error(f"Error sending ICE candidate: {e}")
            return False
