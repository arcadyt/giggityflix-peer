import io
import logging
import os
import uuid
from pathlib import Path
from typing import List, Optional

import aiohttp

from src import config
from giggityflix_peer.models.media import MediaFile, Screenshot
from giggityflix_peer.services.db_service import db_service

logger = logging.getLogger(__name__)

try:
    # Try to import OpenCV for screenshot capture
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    logger.warning("OpenCV not available, using placeholder screenshots")
    OPENCV_AVAILABLE = False


class ScreenshotService:
    """Service for capturing and managing screenshots."""
    
    def __init__(self):
        """Initialize the screenshot service."""
        self.screenshot_dir = Path(config.peer.data_dir) / "screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)
    
    async def capture_screenshots(self, media_file: MediaFile, quantity: int = 1) -> List[Screenshot]:
        """Capture screenshots from a media file."""
        if not media_file.path.exists():
            logger.error(f"Media file does not exist: {media_file.path}")
            return []
        
        if media_file.media_type.value != "video":
            logger.error(f"Cannot capture screenshots from non-video file: {media_file.path}")
            return []
        
        try:
            # Determine the screenshot timestamps
            timestamps = self._calculate_screenshot_timestamps(media_file, quantity)
            
            screenshots = []
            for i, timestamp in enumerate(timestamps):
                # Generate a unique ID for the screenshot
                screenshot_id = str(uuid.uuid4())
                
                # Define the screenshot path
                screenshot_path = self.screenshot_dir / f"{media_file.luid}_{int(timestamp)}_{screenshot_id}.jpg"
                
                # Capture the screenshot
                success, width, height = await self._capture_screenshot(media_file.path, screenshot_path, timestamp)
                
                if success:
                    # Create the screenshot object
                    screenshot = Screenshot(
                        id=screenshot_id,
                        media_luid=media_file.luid,
                        timestamp=timestamp,
                        path=screenshot_path,
                        width=width,
                        height=height
                    )
                    
                    # Add to the result list
                    screenshots.append(screenshot)
                    
                    # Save to the database
                    await db_service.add_screenshot(screenshot)
            
            return screenshots
        
        except Exception as e:
            logger.error(f"Error capturing screenshots: {e}", exc_info=True)
            return []
    
    async def upload_screenshots(self, screenshots: List[Screenshot], upload_endpoint: str, upload_token: str) -> bool:
        """Upload screenshots to the specified endpoint."""
        if not screenshots:
            logger.warning("No screenshots to upload")
            return False
        
        try:
            # Set up the headers with the auth token
            headers = {
                "Authorization": f"Bearer {upload_token}"
            }
            
            # Upload each screenshot
            async with aiohttp.ClientSession() as session:
                for screenshot in screenshots:
                    # Read the screenshot data
                    with open(screenshot.path, "rb") as f:
                        data = f.read()
                    
                    # Create the form data
                    form = aiohttp.FormData()
                    form.add_field(
                        "file",
                        io.BytesIO(data),
                        filename=screenshot.path.name,
                        content_type="image/jpeg"
                    )
                    
                    # Upload the screenshot
                    async with session.post(upload_endpoint, data=form, headers=headers) as response:
                        if response.status != 200:
                            logger.error(f"Error uploading screenshot {screenshot.id}: {response.status}")
                            return False
                        
                        logger.info(f"Uploaded screenshot {screenshot.id}")
            
            return True
        
        except Exception as e:
            logger.error(f"Error uploading screenshots: {e}", exc_info=True)
            return False
    
    def _calculate_screenshot_timestamps(self, media_file: MediaFile, quantity: int) -> List[float]:
        """Calculate the timestamps for screenshots."""
        if not media_file.duration_seconds:
            # Assume a default duration if not available
            duration = 60.0  # 1 minute
        else:
            duration = media_file.duration_seconds
        
        # Skip the first and last 5% of the video
        usable_duration = duration * 0.9
        start_time = duration * 0.05
        
        # Calculate evenly spaced timestamps
        if quantity == 1:
            # If only one screenshot is requested, take it from the middle
            return [start_time + (usable_duration / 2)]
        else:
            # Otherwise, distribute them evenly
            return [
                start_time + (usable_duration * i / (quantity - 1))
                for i in range(quantity)
            ]
    
    async def _capture_screenshot(self, video_path: Path, output_path: Path, timestamp: float) -> tuple[bool, Optional[int], Optional[int]]:
        """Capture a screenshot from a video at the specified timestamp."""
        if not OPENCV_AVAILABLE:
            # Create a placeholder image
            # In a real implementation, we would use ffmpeg or another tool
            # For now, just create an empty file
            with open(output_path, "wb") as f:
                f.write(b"placeholder")
            
            return True, 640, 480
        
        try:
            # Open the video file
            video = cv2.VideoCapture(str(video_path))
            
            # Check if the video opened successfully
            if not video.isOpened():
                logger.error(f"Could not open video file: {video_path}")
                return False, None, None
            
            # Get the video frame rate
            fps = video.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30  # Default to 30 fps if not available
            
            # Calculate the frame number from the timestamp
            frame_number = int(timestamp * fps)
            
            # Set the video position to the frame
            video.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            
            # Read the frame
            success, frame = video.read()
            
            # Release the video
            video.release()
            
            if not success:
                logger.error(f"Could not read frame at timestamp {timestamp} from {video_path}")
                return False, None, None
            
            # Get the frame dimensions
            height, width = frame.shape[:2]
            
            # Save the frame as a JPEG
            cv2.imwrite(str(output_path), frame)
            
            return True, width, height
        
        except Exception as e:
            logger.error(f"Error capturing screenshot: {e}", exc_info=True)
            return False, None, None


# Create a singleton service instance
screenshot_service = ScreenshotService()
