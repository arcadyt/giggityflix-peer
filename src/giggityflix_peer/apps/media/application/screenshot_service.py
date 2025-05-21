"""Service for capturing and managing media screenshots."""
import asyncio
import io
import logging
import os
import time
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from django.conf import settings

from ..domain.models import Media, Screenshot
from ..infrastructure.repositories import get_media_repository, get_screenshot_repository

logger = logging.getLogger(__name__)


class ScreenshotQualityCalculator:
    """Utility for calculating screenshot quality."""
    
    @staticmethod
    def calculate_quality_score(frame_data: bytes) -> float:
        """Calculate Laplacian variance score for a frame."""
        np_array = np.frombuffer(frame_data, dtype=np.uint8)
        frame = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        if frame is None:
            return -1
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()


class ScreenshotPositionCalculator:
    """Utility for calculating optimal screenshot positions."""
    
    @staticmethod
    def calculate_frame_positions(start_frame: int, usable_frames: int, quantity: int) -> List[int]:
        """Calculate evenly distributed frame positions."""
        if quantity <= 0:
            return []
        
        if usable_frames <= 0:
            return [start_frame]
        
        if quantity == 1:
            return [start_frame + (usable_frames // 2)]
        
        return [
            start_frame + int(usable_frames * i / (quantity - 1))
            for i in range(quantity)
        ]
    
    @staticmethod
    def calculate_quality_radius(positions: List[int], frame_rate: float) -> int:
        """Determine optimal search radius based on positions and frame rate."""
        distances = [
            positions[i + 1] - positions[i] for i in range(len(positions) - 1)
        ] if len(positions) > 1 else []
        
        min_distance = min(distances) if distances else float('inf')
        
        return min(
            int(frame_rate), min_distance // 2
        ) if min_distance != float('inf') else int(frame_rate)
    
    @staticmethod
    def get_valid_frame_range(target_pos: int, radius: int, total_frames: int) -> Tuple[int, int]:
        """Calculate valid frame range within video bounds."""
        start_pos = max(0, target_pos - radius)
        end_pos = min(total_frames - 1, target_pos + radius)
        return start_pos, end_pos


class ScreenshotService:
    """Service for capturing and managing media screenshots."""
    
    def __init__(self):
        """Initialize the screenshot service."""
        self.media_repository = get_media_repository()
        self.screenshot_repository = get_screenshot_repository()
        self.screenshots_dir = Path(settings.MEDIA_ROOT) / 'screenshots'
        os.makedirs(self.screenshots_dir, exist_ok=True)
    
    def capture_for_media(self, media_luid: str, quantity: int = 3) -> List[Screenshot]:
        """
        Capture screenshots for a media file.
        
        Args:
            media_luid: Local ID of the media file
            quantity: Number of screenshots to capture
            
        Returns:
            List of captured Screenshot objects
        """
        # Get media file
        media = self.media_repository.get_by_luid(media_luid)
        if not media:
            logger.error(f"Media file not found: {media_luid}")
            return []
        
        # Check if media exists and is a video
        if not media.exists() or media.media_type != 'video':
            logger.error(f"Media file not found or not a video: {media.path}")
            return []
        
        try:
            # Extract frames
            screenshots = self._extract_screenshots(media, quantity)
            
            # Save screenshots
            for screenshot in screenshots:
                self.screenshot_repository.save(screenshot)
            
            return screenshots
        
        except Exception as e:
            logger.error(f"Error capturing screenshots: {e}")
            return []
    
    def get_screenshots(self, media_luid: str) -> List[Screenshot]:
        """Get all screenshots for a media file."""
        return self.screenshot_repository.get_for_media(media_luid)
    
    def _extract_screenshots(self, media: Media, quantity: int) -> List[Screenshot]:
        """Extract screenshots from a video file."""
        video_path = media.path
        
        # Open video
        video = cv2.VideoCapture(video_path)
        if not video.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        
        try:
            # Get video properties
            frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_rate = video.get(cv2.CAP_PROP_FPS)
            width = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # Calculate frame positions
            frame_positions = ScreenshotPositionCalculator.calculate_frame_positions(
                start_frame=max(1, int(frames * 0.05)),
                usable_frames=int(frames * 0.9),
                quantity=quantity
            )
            
            quality_radius = ScreenshotPositionCalculator.calculate_quality_radius(
                frame_positions, frame_rate
            )
            
            screenshots = []
            
            # Process each position
            for pos in frame_positions:
                start_pos, end_pos = ScreenshotPositionCalculator.get_valid_frame_range(
                    pos, quality_radius, frames
                )
                
                # Extract frames in range
                frames_data = []
                video.set(cv2.CAP_PROP_POS_FRAMES, start_pos)
                
                for _ in range(end_pos - start_pos + 1):
                    success, frame = video.read()
                    if not success or frame is None:
                        break
                    
                    # Convert frame to JPEG
                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    frame_data = buffer.tobytes()
                    frames_data.append(frame_data)
                
                if not frames_data:
                    continue
                
                # Calculate quality scores
                scores = [
                    ScreenshotQualityCalculator.calculate_quality_score(frame_data)
                    for frame_data in frames_data
                ]
                
                # Select best frame
                best_frame_data = None
                if any(s > 0 for s in scores):
                    best_index = scores.index(max(scores))
                    best_frame_data = frames_data[best_index]
                else:
                    best_frame_data = frames_data[0]
                
                if best_frame_data:
                    # Save screenshot to file
                    screenshot_id = str(uuid.uuid4())
                    file_name = f"{media.luid}_{screenshot_id}.jpg"
                    screenshot_path = str(self.screenshots_dir / file_name)
                    
                    with open(screenshot_path, 'wb') as f:
                        f.write(best_frame_data)
                    
                    # Create screenshot object
                    screenshot = Screenshot(
                        id=screenshot_id,
                        media_luid=media.luid,
                        path=screenshot_path,
                        timestamp=pos / frame_rate,
                        width=width,
                        height=height
                    )
                    
                    screenshots.append(screenshot)
            
            return screenshots
        
        finally:
            video.release()


# Singleton instance
_screenshot_service = None


def get_screenshot_service() -> ScreenshotService:
    """Get or create a ScreenshotService instance."""
    global _screenshot_service
    if _screenshot_service is None:
        _screenshot_service = ScreenshotService()
    return _screenshot_service
