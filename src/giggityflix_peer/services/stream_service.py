import asyncio
import logging
import time
import uuid
from typing import Dict, Optional

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay

from src import config
from giggityflix_peer.models.media import MediaFile
from giggityflix_peer.services.db_service import db_service

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
    
    async def create_offer(self) -> RTCSessionDescription:
        """Create a WebRTC offer for this session."""
        # Create a new peer connection
        self.peer_connection = RTCPeerConnection(self._get_rtc_config())
        
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
        
        return RTCSessionDescription(sdp=self.peer_connection.localDescription.sdp, type=self.peer_connection.localDescription.type)
    
    async def handle_answer(self, session_description: RTCSessionDescription) -> None:
        """Handle a WebRTC answer."""
        if not self.peer_connection:
            raise RuntimeError("Peer connection not initialized")
        
        await self.peer_connection.setRemoteDescription(session_description)
        
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
        stun_servers = config.webrtc.stun_servers
        turn_servers = config.webrtc.turn_servers
        
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
            await self._close_session(session_id)
    
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
            # Generate a session ID
            session_id = str(uuid.uuid4())
            
            # Create a session
            session = StreamSession(session_id, media_file)
            
            # Create an offer
            offer = await session.create_offer()
            
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
            
            # Handle the answer
            await session.handle_answer(session_description)
            
            logger.info(f"Handled answer for session {session_id}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error handling answer for session {session_id}: {e}", exc_info=True)
            return False
    
    async def get_session(self, session_id: str) -> Optional[StreamSession]:
        """Get a streaming session by ID."""
        return self.active_sessions.get(session_id)
    
    async def close_session(self, session_id: str) -> bool:
        """Close a streaming session."""
        return await self._close_session(session_id)
    
    async def _close_session(self, session_id: str) -> bool:
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
                    await self._close_session(session_id)
                
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
