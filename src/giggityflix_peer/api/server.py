import logging
from pathlib import Path

from aiohttp import web

from giggityflix_peer.config import config
from giggityflix_peer.services import screenshot_service
from giggityflix_peer.services import stream_service
from giggityflix_peer.services.config_service import config_service, get_drive_info_for_path
from giggityflix_peer.services.db_service import db_service
from giggityflix_peer.services.disk_io_service import disk_io_service

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
        self.app.router.add_post("/api/stream/{session_id}/ice", self.handle_ice_candidate)
        self.app.router.add_delete("/api/stream/{session_id}", self.handle_close_stream)

        # Screenshots routes
        self.app.router.add_post("/api/screenshots/{luid}", self.handle_capture_screenshots)

        # Settings routes
        self.app.router.add_get("/api/settings", self.handle_get_settings)
        self.app.router.add_get("/api/settings/{key}", self.handle_get_setting)
        self.app.router.add_put("/api/settings/{key}", self.handle_update_setting)
        
        # Drive configuration routes
        self.app.router.add_get("/api/drives", self.handle_get_drives)
        self.app.router.add_get("/api/drives/{drive_id}", self.handle_get_drive)
        self.app.router.add_put("/api/drives/{drive_id}", self.handle_update_drive)
        self.app.router.add_get("/api/drives/physical", self.handle_get_physical_drives)

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
            
    # Settings route handlers
            
    async def handle_get_settings(self, request: web.Request) -> web.Response:
        """Handle a request to get all settings."""
        try:
            # Get only editable settings
            settings = await config_service.get_all(editable_only=True)
            
            # Convert to list for JSON response
            settings_list = [
                {
                    "key": key,
                    "value": value["value"],
                    "value_type": value["value_type"],
                    "description": value["description"],
                    "last_updated": value["last_updated"]
                }
                for key, value in settings.items()
            ]
            
            return web.json_response({"settings": settings_list})
            
        except Exception as e:
            logger.error(f"Error handling get settings request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_get_setting(self, request: web.Request) -> web.Response:
        """Handle a request to get a specific setting."""
        try:
            key = request.match_info["key"]
            
            # Get setting from config service
            setting = await config_service.get_setting(key)
            
            if not setting:
                return web.json_response({"error": f"Setting {key} not found"}, status=404)
                
            if not setting["editable"]:
                return web.json_response({"error": f"Setting {key} is not editable"}, status=403)
                
            return web.json_response({
                "key": key,
                "value": setting["value"],
                "value_type": setting["value_type"],
                "description": setting["description"],
                "last_updated": setting["last_updated"]
            })
            
        except Exception as e:
            logger.error(f"Error handling get setting request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_update_setting(self, request: web.Request) -> web.Response:
        """Handle a request to update a setting."""
        try:
            key = request.match_info["key"]
            
            # Get request body
            data = await request.json()
            
            if "value" not in data:
                return web.json_response({"error": "Missing value in request"}, status=400)
                
            # Update setting
            try:
                await config_service.set(key, data["value"])
            except ValueError as ve:
                return web.json_response({"error": str(ve)}, status=400)
                
            # Get updated setting
            setting = await config_service.get_setting(key)
            
            return web.json_response({
                "key": key,
                "value": setting["value"],
                "value_type": setting["value_type"],
                "description": setting["description"],
                "last_updated": setting["last_updated"]
            })
            
        except Exception as e:
            logger.error(f"Error handling update setting request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    # Drive configuration route handlers
    
    async def handle_get_drives(self, request: web.Request) -> web.Response:
        """Handle a request to get all drive configurations."""
        try:
            # Get all drive configurations
            drive_configs = await config_service.get_all_drive_configs()
            
            # Convert to list for JSON response
            drive_list = [
                {
                    "drive_id": drive_id,
                    "physical_drive": config["physical_drive"],
                    "concurrent_operations": config["concurrent_operations"],
                    "last_updated": config["last_updated"]
                }
                for drive_id, config in drive_configs.items()
            ]
            
            return web.json_response({"drives": drive_list})
            
        except Exception as e:
            logger.error(f"Error handling get drives request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_get_drive(self, request: web.Request) -> web.Response:
        """Handle a request to get a specific drive configuration."""
        try:
            drive_id = request.match_info["drive_id"]
            
            # Get drive configuration
            config = await config_service.get_drive_config(drive_id)
            
            if not config:
                return web.json_response({"error": f"Drive configuration not found: {drive_id}"}, status=404)
                
            return web.json_response({
                "drive_id": config["drive_id"],
                "physical_drive": config["physical_drive"],
                "concurrent_operations": config["concurrent_operations"],
                "last_updated": config["last_updated"]
            })
            
        except Exception as e:
            logger.error(f"Error handling get drive request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)

    async def handle_update_drive(self, request: web.Request) -> web.Response:
        """Handle a request to update a drive configuration."""
        try:
            drive_id = request.match_info["drive_id"]

            # Get request body
            data = await request.json()

            if "concurrent_operations" not in data:
                return web.json_response({"error": "Missing concurrent_operations in request"}, status=400)

            # Validate concurrent_operations
            concurrent_operations = data["concurrent_operations"]
            if not isinstance(concurrent_operations, int) or concurrent_operations < 1:
                return web.json_response({"error": "concurrent_operations must be a positive integer"}, status=400)

            # Update drive configuration
            await config_service.set_drive_config(drive_id, concurrent_operations)

            # Update disk I/O service semaphore limits to apply the new configuration
            await disk_io_service.update_semaphore_limits()

            # Get updated configuration
            config = await config_service.get_drive_config(drive_id)

            return web.json_response({
                "drive_id": config["drive_id"],
                "physical_drive": config["physical_drive"],
                "concurrent_operations": config["concurrent_operations"],
                "last_updated": config["last_updated"]
            })

        except Exception as e:
            logger.error(f"Error handling update drive request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)
    
    async def handle_get_physical_drives(self, request: web.Request) -> web.Response:
        """Handle a request to get physical drive mappings."""
        try:
            # Get physical drive mappings
            physical_drives = await config_service.get_physical_drives()
            
            # Convert to list for JSON response
            drive_list = [
                {
                    "physical_drive": physical_drive,
                    "logical_drives": logical_drives
                }
                for physical_drive, logical_drives in physical_drives.items()
            ]
            
            return web.json_response({"physical_drives": drive_list})
            
        except Exception as e:
            logger.error(f"Error handling get physical drives request: {e}", exc_info=True)
            return web.json_response({"error": str(e)}, status=500)


# Create a singleton server instance
api_server = ApiServer()
