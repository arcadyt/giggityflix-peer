"""Service for handling media streaming via WebRTC."""
import asyncio
import logging
import time
import uuid
from typing import Dict, Optional, Tuple

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from django.conf import settings

from ..domain.models import Media
from ..infrastructure.repositories import get_media_repository
from .grpc_service import get_media_grpc_service

logger = logging.getLogger(__name__)


class StreamSession:
    """Represents an active streaming session."""

    def __init__(self, session_id: str, media: Media):
        self.session_id = session_id
        self.media = media
        self.peer_connection: Optional[RTCPeerConnection] = None
        self.created_at = time.time()
        self.last_activity = time.time()
        self.player: Optional[MediaPlayer] = None
        self.relay = MediaRelay()

    async def create_offer(self) -> RTCSessionDescription:
        """Create WebRTC offer for this session."""
        self.peer_connection = RTCPeerConnection(self._get_rtc_config())

        @self.peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.debug(f"Connection state changed: {self.peer_connection.connectionState}")
            self.last_activity = time.time()

        # Create media player
        self.player = MediaPlayer(str(self.media.path))

        # Add tracks
        if self.player.audio:
            audio_track = self.relay.subscribe(self.player.audio)
            self.peer_connection.addTrack(audio_track)

        if self.player.video:
            video_track = self.relay.subscribe(self.player.video)
            self.peer_connection.addTrack(video_track)

        # Create offer
        offer = await self.peer_connection.createOffer()
        await self.peer_connection.setLocalDescription(offer)

        self.last_activity = time.time()
        return RTCSessionDescription(
            sdp=self.peer_connection.localDescription.sdp,
            type=self.peer_connection.localDescription.type
        )

    async def handle_answer(self, session_description: RTCSessionDescription) -> None:
        """Handle WebRTC answer."""
        if not self.peer_connection:
            raise RuntimeError("Peer connection not initialized")

        await self.peer_connection.setRemoteDescription(session_description)
        self.last_activity = time.time()

    async def close(self) -> None:
        """Close streaming session."""
        if self.peer_connection:
            await self.peer_connection.close()
            self.peer_connection = None

        if self.player:
            self.player.stop()
            self.player = None

    def _get_rtc_config(self) -> RTCConfiguration:
        """Get WebRTC configuration."""
        stun_servers = getattr(settings, 'WEBRTC_STUN_SERVERS', ['stun:stun.l.google.com:19302'])
        turn_servers = getattr(settings, 'WEBRTC_TURN_SERVERS', [])

        ice_servers = []

        # Add STUN servers
        for server in stun_servers:
            ice_servers.append({"urls": server})

        # Add TURN servers
        for server in turn_servers:
            ice_server = {"urls": server}
            turn_username = getattr(settings, 'WEBRTC_TURN_USERNAME', None)
            turn_password = getattr(settings, 'WEBRTC_TURN_PASSWORD', None)
            
            if turn_username:
                ice_server["username"] = turn_username
            if turn_password:
                ice_server["credential"] = turn_password
                
            ice_servers.append(ice_server)

        return RTCConfiguration(iceServers=ice_servers)


class StreamService:
    """Service for handling media streaming."""

    def __init__(self):
        self.media_repository = get_media_repository()
        self.grpc_service = get_media_grpc_service()
        self.active_sessions: Dict[str, StreamSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start stream service."""
        logger.info("Starting stream service")
        self._cleanup_task = asyncio.create_task(self._cleanup_sessions())

    async def stop(self) -> None:
        """Stop stream service."""
        logger.info("Stopping stream service")
        self._stop_event.set()

        if self._cleanup_task:
            await self._cleanup_task

        # Close all active sessions
        for session_id in list(self.active_sessions.keys()):
            await self.close_session(session_id)

    async def create_session(self, media_luid: str) -> Optional[Tuple[str, RTCSessionDescription]]:
        """Create new streaming session for media file."""
        media = self.media_repository.get_by_luid(media_luid)
        if not media:
            logger.error(f"Media file not found: {media_luid}")
            return None

        if not media.exists():
            logger.error(f"Media file does not exist: {media.path}")
            return None

        try:
            session_id = str(uuid.uuid4())
            
            # Create stream session with edge service if available
            if media.catalog_id and self.grpc_service.is_connected():
                edge_session_id, remote_sdp = await self.grpc_service.grpc_client.create_stream_session(media.catalog_id)
                if edge_session_id:
                    session_id = edge_session_id

            # Create local session
            session = StreamSession(session_id, media)
            offer = await session.create_offer()

            # Store session
            self.active_sessions[session_id] = session

            # Increment view count
            media.increment_view_count()
            self.media_repository.save(media)

            logger.info(f"Created streaming session {session_id} for media {media_luid}")
            return session_id, offer

        except Exception as e:
            logger.error(f"Error creating streaming session: {e}")
            return None

    async def handle_answer(self, session_id: str, answer_sdp: str, answer_type: str) -> bool:
        """Handle WebRTC answer for session."""
        session = self.active_sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return False

        try:
            session_description = RTCSessionDescription(sdp=answer_sdp, type=answer_type)
            await session.handle_answer(session_description)
            logger.info(f"Handled answer for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error handling answer for session {session_id}: {e}")
            return False

    async def close_session(self, session_id: str) -> bool:
        """Close streaming session."""
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        try:
            await session.close()
            del self.active_sessions[session_id]
            logger.info(f"Closed streaming session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}")
            return False

    async def _cleanup_sessions(self) -> None:
        """Periodically clean up inactive sessions."""
        inactive_timeout = getattr(settings, 'STREAM_INACTIVE_TIMEOUT', 300)  # 5 minutes

        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                inactive_sessions = []

                for session_id, session in self.active_sessions.items():
                    if current_time - session.last_activity > inactive_timeout:
                        inactive_sessions.append(session_id)

                for session_id in inactive_sessions:
                    logger.info(f"Closing inactive session {session_id}")
                    await self.close_session(session_id)

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logger.error(f"Error in session cleanup: {e}")
                await asyncio.sleep(60)


# Singleton instance
_stream_service = None


def get_stream_service() -> StreamService:
    """Get or create StreamService instance."""
    global _stream_service
    if _stream_service is None:
        _stream_service = StreamService()
    return _stream_service
