import logging
from pathlib import Path

from aiohttp import web

from giggityflix_peer.config import config
from giggityflix_peer.services.db_service import db_service
from giggityflix_peer.services import screenshot_service
from giggityflix_peer.services import stream_service


logger = logging.getLogger(__name__)


class ApiServer:
    """REST API server for the peer service."""
    
    def __init__(self):
        """Initialize the API server."""
        self.app = web.Application()
        self.port = config.peer.http_port
        self.runner = None
        self.site = None
        
        # Set up routes
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """Set up the API routes."""
        # API routes
        self.app.router.add_get("/api/media", self.handle_get_media)
        self.app.router.add_get("/api/media/{luid}", self.handle_get_media_by_id)
        self.app.router.add_get("/api/media/{luid}/screenshots", self.handle_get_screenshots)
        
        # Streaming routes
        self.app.router.add_post("/api/stream/{luid}", self.handle_create_stream)
        self.app.router.add_post("/api/stream/{session_id}/answer", self.handle_stream_answer)
        self.app.router.add_delete("/api/stream/{session_id}", self.handle_close_stream)
        
        # Screenshots routes
        self.app.router.add_post("/api/screenshots/{luid}", self.handle_capture_screenshots)
        
        # Static files for screenshots
        self.app.router.add_static("/screenshots", Path(config.peer.data_dir) / "screenshots")
    
    async def start(self) -> None:
        """Start the API server."""
        logger.info(f"Starting API server on port {self.port}")
        
        # Create the runner
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        # Create the site
        self.site = web.TCPSite(self.runner, "0.0.0.0", self.port)
        await self.site.start()
        
        logger.info(f"API server running on http://0.0.0.0:{self.port}")
    
    async def stop(self) -> None:
        """Stop the API server."""
        logger.info("Stopping API server")
        
        if self.site:
            await self.site.stop()
            self.site = None
        
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        
        logger.info("API server stopped")
    
    # API route handlers
    
    async def handle_get_media(self, request: web.Request) -> web.Response:
        """Handle a request to get all media files."""
        try:
            # Get all media files from the database
            media_files = await db_service.get_all_media_files()
            
            # Convert to a list of dictionaries
            media_list = []
            for media_file in media_files:
                media_dict = {
                    "luid": media_file.luid,
                    "catalog_id": media_file.catalog_id,
                    "path": str(media_file.path),
                    "relative_path": media_file.relative_path,
                    "size_bytes": media_file.size_bytes,
                    "media_type": media_file.media_type.value,
                    "status": media_file.status.value,
                    "duration_seconds": media_file.duration_seconds,
                    "width": media_file.width,
                    "height": media_file.height,
                    "codec": media_file.codec,
                    "bitrate": media_file.bitrate,
                    "framerate": media_file.framerate,
                    "view_count": media_file.view_count,
                    "created_at": media_file.created_at.isoformat() if media_file.created_at else None,
                    "last_viewed": media_file.last_viewed.isoformat() if media_file.last_viewed else None
                }
                media_list.append(media_dict)
            
            return web.json_response({"media": media_list})
        
        except Exception as e:
            logger.error(f"Error handling get media request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_get_media_by_id(self, request: web.Request) -> web.Response:
        """Handle a request to get a media file by ID."""
        try:
            # Get the media LUID from the URL
            luid = request.match_info["luid"]
            
            # Get the media file from the database
            media_file = await db_service.get_media_file(luid)
            
            if not media_file:
                return web.json_response({"error": f"Media file not found: {luid}"}, status=404)
            
            # Convert to a dictionary
            media_dict = {
                "luid": media_file.luid,
                "catalog_id": media_file.catalog_id,
                "path": str(media_file.path),
                "relative_path": media_file.relative_path,
                "size_bytes": media_file.size_bytes,
                "media_type": media_file.media_type.value,
                "status": media_file.status.value,
                "duration_seconds": media_file.duration_seconds,
                "width": media_file.width,
                "height": media_file.height,
                "codec": media_file.codec,
                "bitrate": media_file.bitrate,
                "framerate": media_file.framerate,
                "view_count": media_file.view_count,
                "created_at": media_file.created_at.isoformat() if media_file.created_at else None,
                "last_viewed": media_file.last_viewed.isoformat() if media_file.last_viewed else None,
                "hashes": media_file.hashes
            }
            
            return web.json_response({"media": media_dict})
        
        except Exception as e:
            logger.error(f"Error handling get media by ID request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_get_screenshots(self, request: web.Request) -> web.Response:
        """Handle a request to get screenshots for a media file."""
        try:
            # Get the media LUID from the URL
            luid = request.match_info["luid"]
            
            # Get the screenshots from the database
            screenshots = await db_service.get_screenshots_for_media(luid)
            
            # Convert to a list of dictionaries
            screenshot_list = []
            for screenshot in screenshots:
                screenshot_dict = {
                    "id": screenshot.id,
                    "media_luid": screenshot.media_luid,
                    "timestamp": screenshot.timestamp,
                    "path": str(screenshot.path),
                    "url": f"/screenshots/{screenshot.path.name}",
                    "width": screenshot.width,
                    "height": screenshot.height,
                    "created_at": screenshot.created_at.isoformat() if screenshot.created_at else None
                }
                screenshot_list.append(screenshot_dict)
            
            return web.json_response({"screenshots": screenshot_list})
        
        except Exception as e:
            logger.error(f"Error handling get screenshots request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_create_stream(self, request: web.Request) -> web.Response:
        """Handle a request to create a streaming session."""
        try:
            # Get the media LUID from the URL
            luid = request.match_info["luid"]
            
            # Create a streaming session
            result = await stream_service.create_session(luid)
            
            if not result:
                return web.json_response({"error": "Failed to create streaming session"}, status=500)
            
            session_id, offer = result
            
            # Return the session ID and offer
            return web.json_response({
                "session_id": session_id,
                "offer": {
                    "sdp": offer.sdp,
                    "type": offer.type
                }
            })
        
        except Exception as e:
            logger.error(f"Error handling create stream request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_stream_answer(self, request: web.Request) -> web.Response:
        """Handle a WebRTC answer for a streaming session."""
        try:
            # Get the session ID from the URL
            session_id = request.match_info["session_id"]
            
            # Get the answer from the request body
            data = await request.json()
            
            if "sdp" not in data or "type" not in data:
                return web.json_response({"error": "Missing sdp or type in request"}, status=400)
            
            # Handle the answer
            success = await stream_service.handle_answer(session_id, data["sdp"], data["type"])
            
            if not success:
                return web.json_response({"error": "Failed to handle answer"}, status=500)
            
            return web.json_response({"status": "ok"})
        
        except Exception as e:
            logger.error(f"Error handling stream answer request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_close_stream(self, request: web.Request) -> web.Response:
        """Handle a request to close a streaming session."""
        try:
            # Get the session ID from the URL
            session_id = request.match_info["session_id"]
            
            # Close the session
            success = await stream_service.close_session(session_id)
            
            if not success:
                return web.json_response({"error": "Failed to close session"}, status=500)
            
            return web.json_response({"status": "ok"})
        
        except Exception as e:
            logger.error(f"Error handling close stream request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_capture_screenshots(self, request: web.Request) -> web.Response:
        """Handle a request to capture screenshots for a media file."""
        try:
            # Get the media LUID from the URL
            luid = request.match_info["luid"]
            
            # Get the quantity from the query parameters
            try:
                quantity = int(request.query.get("quantity", "3"))
            except ValueError:
                quantity = 3
            
            # Get the media file from the database
            media_file = await db_service.get_media_file(luid)
            
            if not media_file:
                return web.json_response({"error": f"Media file not found: {luid}"}, status=404)
            
            # Capture screenshots
            screenshots = await screenshot_service.capture_screenshots(media_file, quantity)
            
            if not screenshots:
                return web.json_response({"error": "Failed to capture screenshots"}, status=500)
            
            # Convert to a list of dictionaries
            screenshot_list = []
            for screenshot in screenshots:
                screenshot_dict = {
                    "id": screenshot.id,
                    "media_luid": screenshot.media_luid,
                    "timestamp": screenshot.timestamp,
                    "path": str(screenshot.path),
                    "url": f"/screenshots/{screenshot.path.name}",
                    "width": screenshot.width,
                    "height": screenshot.height,
                    "created_at": screenshot.created_at.isoformat() if screenshot.created_at else None
                }
                screenshot_list.append(screenshot_dict)
            
            return web.json_response({"screenshots": screenshot_list})
        
        except Exception as e:
            logger.error(f"Error handling capture screenshots request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)


# Create a singleton server instance
api_server = ApiServer()
