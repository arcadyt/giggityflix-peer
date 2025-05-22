import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay

from giggityflix_peer.config import config
from giggityflix_peer.models.media import MediaFile
from giggityflix_peer.old_services.db_service import db_service
from giggityflix_peer.apps.media.fixme_grpc import edge_client

logger = logging.getLogger(__name__)


class StreamSession:
    """Represents an active streaming session."""

    def __init__(self, session_id: str, media_file: MediaFile):
        """Initialize a streaming session."""
        self.session_id = session_id
        self.media_file = media_file
        self.peer_connection: Optional[RTCPeerConnection] = None
        self.created_at = time.time()
        self.last_activity = time.time()
        self.player: Optional[MediaPlayer] = None
        self.relay = MediaRelay()
        self.ice_candidates: List[Dict] = []  # Store ICE candidates to send later

    async def create_offer(self) -> RTCSessionDescription:
        """Create a WebRTC offer for this session."""
        # Create a new peer connection
        self.peer_connection = RTCPeerConnection(self._get_rtc_config())

        # Set up event handlers
        @self.peer_connection.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                # Store ICE candidate to send later
                self.ice_candidates.append({
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex
                })

                # Send ICE candidate to edge service
                await edge_client.send_ice_candidate(
                    self.session_id,
                    candidate.candidate,
                    candidate.sdpMid,
                    candidate.sdpMLineIndex
                )

        @self.peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.debug(f"Connection state changed: {self.peer_connection.connectionState}")
            self.last_activity = time.time()

        # Create a media player for the file
        self.player = MediaPlayer(str(self.media_file.path))

        # Add media tracks to the peer connection
        if self.player.audio:
            audio_track = self.relay.subscribe(self.player.audio)
            self.peer_connection.addTrack(audio_track)

        if self.player.video:
            video_track = self.relay.subscribe(self.player.video)
            self.peer_connection.addTrack(video_track)

        # Create an offer
        offer = await self.peer_connection.createOffer()
        await self.peer_connection.setLocalDescription(offer)

        # Update last activity time
        self.last_activity = time.time()

        return RTCSessionDescription(sdp=self.peer_connection.localDescription.sdp,
                                     type=self.peer_connection.localDescription.type)

    async def handle_answer(self, session_description: RTCSessionDescription) -> None:
        """Handle a WebRTC answer."""
        if not self.peer_connection:
            raise RuntimeError("Peer connection not initialized")

        await self.peer_connection.setRemoteDescription(session_description)

        # Update last activity time
        self.last_activity = time.time()

    async def handle_ice_candidate(self, candidate: str, sdp_mid: str, sdp_mline_index: int) -> None:
        """Handle an ICE candidate from the remote peer."""
        if not self.peer_connection:
            raise RuntimeError("Peer connection not initialized")

        await self.peer_connection.addIceCandidate({
            "candidate": candidate,
            "sdpMid": sdp_mid,
            "sdpMLineIndex": sdp_mline_index
        })

        # Update last activity time
        self.last_activity = time.time()

    async def close(self) -> None:
        """Close the streaming session."""
        if self.peer_connection:
            await self.peer_connection.close()
            self.peer_connection = None

        if self.player:
            self.player.stop()
            self.player = None

    def _get_rtc_config(self) -> RTCConfiguration:
        """Get the WebRTC configuration."""
        stun_servers = [config.webrtc.stun_server] if config.webrtc.stun_server else []
        turn_servers = [config.webrtc.turn_server] if config.webrtc.turn_server else []

        ice_servers = []

        # Add STUN servers
        for server in stun_servers:
            ice_servers.append({"urls": server})

        # Add TURN servers
        for server in turn_servers:
            ice_server = {"urls": server}

            if config.webrtc.turn_username:
                ice_server["username"] = config.webrtc.turn_username

            if config.webrtc.turn_password:
                ice_server["credential"] = config.webrtc.turn_password

            ice_servers.append(ice_server)

        return RTCConfiguration(iceServers=ice_servers)


class StreamService:
    """Service for handling media streaming."""

    def __init__(self):
        """Initialize the stream service."""
        self.active_sessions: Dict[str, StreamSession] = {}
        self._cleanup_task = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the stream service."""
        logger.info("Starting stream service")

        # Start the session cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_sessions())

    async def stop(self) -> None:
        """Stop the stream service."""
        logger.info("Stopping stream service")

        # Signal the cleanup task to stop
        self._stop_event.set()

        # Wait for the cleanup task to finish
        if self._cleanup_task:
            await self._cleanup_task

        # Close all active sessions
        for session_id, session in list(self.active_sessions.items()):
            await self.close_session(session_id)

    async def create_session(self, media_luid: str) -> Optional[Tuple[str, RTCSessionDescription]]:
        """
        Create a new streaming session for a media file.
        
        Returns:
            A tuple of (session_id, offer) if successful, None otherwise
        """
        # Get the media file
        media_file = await db_service.get_media_file(media_luid)
        if not media_file:
            logger.error(f"Media file not found: {media_luid}")
            return None

        # Check if the file exists
        if not media_file.path.exists():
            logger.error(f"Media file does not exist: {media_file.path}")
            return None

        try:
            # Create a session with the Edge Service if media has catalog ID
            session_id = None
            remote_sdp = None

            if media_file.catalog_id:
                # Use Edge Service to create session
                result = await edge_client.create_stream_session(media_file.catalog_id)
                if result:
                    session_id, remote_sdp = result
                    logger.info(f"Created edge stream session for {media_file.catalog_id}")

            # If edge session failed or not available, generate local session ID
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.info(f"Created local stream session ID: {session_id}")

            # Create a stream session
            session = StreamSession(session_id, media_file)

            # Create a WebRTC offer
            offer = await session.create_offer()

            # Send the offer to the Edge Service if remote SDP available
            if remote_sdp:
                # Process remote SDP as an answer
                remote_description = RTCSessionDescription(sdp=remote_sdp, type="answer")
                await session.handle_answer(remote_description)
            else:
                # For direct peer to client streaming (no Edge server)
                # This is the offer we'll send to the client
                pass

            # Store the session
            self.active_sessions[session_id] = session

            # Update the media file's view count
            await db_service.increment_view_count(media_luid)

            logger.info(f"Created streaming session {session_id} for media {media_luid}")

            return session_id, offer

        except Exception as e:
            logger.error(f"Error creating streaming session: {e}", exc_info=True)
            return None

    async def handle_answer(self, session_id: str, answer_sdp: str, answer_type: str) -> bool:
        """Handle a WebRTC answer for a session."""
        session = self.active_sessions.get(session_id)
        if not session:
            logger.error(f"Session not found: {session_id}")
            return False

        try:
            # Create the session description
            session_description = RTCSessionDescription(sdp=answer_sdp, type=answer_type)

            # Handle the answer locally
            await session.handle_answer(session_description)

            # Also send to Edge Service if needed
            if session.media_file.catalog_id:
                await edge_client.send_sdp_answer(session_id, answer_sdp)

            logger.info(f"Handled answer for session {session_id}")

            # Send any cached ICE candidates
            for ice in session.ice_candidates:
                await edge_client.send_ice_candidate(
                    session_id,
                    ice["candidate"],
                    ice["sdpMid"],
                    ice["sdpMLineIndex"]
                )

            # Clear cached candidates now that they're sent
            session.ice_candidates = []

            return True

        except Exception as e:
            logger.error(f"Error handling answer for session {session_id}: {e}", exc_info=True)
            return False

    async def handle_ice_candidate(self, session_id: str, candidate: str,
                                   sdp_mid: str, sdp_mline_index: int) -> bool:
        """Handle an ICE candidate for a session."""
        session = self.active_sessions.get(session_id)
        if not session:
            logger.error(f"Session not found for ICE candidate: {session_id}")
            return False

        try:
            # Process the ICE candidate locally
            await session.handle_ice_candidate(candidate, sdp_mid, sdp_mline_index)

            # Also send to Edge Service if needed
            if session.media_file.catalog_id:
                await edge_client.send_ice_candidate(session_id, candidate, sdp_mid, sdp_mline_index)

            return True

        except Exception as e:
            logger.error(f"Error handling ICE candidate for {session_id}: {e}")
            return False

    async def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get a streaming session by ID."""
        return self.active_sessions.get(session_id)

    async def close_session(self, session_id: str) -> bool:
        """Close a streaming session and remove it from active sessions."""
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        try:
            # Close the session
            await session.close()

            # Remove from active sessions
            del self.active_sessions[session_id]

            logger.info(f"Closed streaming session {session_id}")

            return True

        except Exception as e:
            logger.error(f"Error closing session {session_id}: {e}", exc_info=True)
            return False

    async def _cleanup_sessions(self) -> None:
        """Periodically clean up inactive sessions."""
        inactive_timeout = 300  # 5 minutes

        while not self._stop_event.is_set():
            try:
                # Get the current time
                current_time = time.time()

                # Find inactive sessions
                inactive_sessions = []
                for session_id, session in self.active_sessions.items():
                    if current_time - session.last_activity > inactive_timeout:
                        inactive_sessions.append(session_id)

                # Close inactive sessions
                for session_id in inactive_sessions:
                    logger.info(f"Closing inactive session {session_id}")
                    await self.close_session(session_id)

                # Wait before checking again
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass

            except Exception as e:
                logger.error(f"Error in session cleanup: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before trying again


# Create a singleton service instance
stream_service = StreamService()
