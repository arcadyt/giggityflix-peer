"""Service for capturing and managing media screenshots."""
import asyncio
import io
import logging
import uuid
from pathlib import Path
from typing import List, Optional

import aiohttp
import cv2
import numpy as np

from giggityflix_peer.core.resource_pool.decorators import io_bound, cpu_bound
from giggityflix_peer.apps.configuration import services as config_service

from ..domain.models import Media, Screenshot
from ..infrastructure.repositories import get_media_repository, get_screenshot_repository
from ..video_file_utils import FramePositionCalculator, FrameQualityCalculator

logger = logging.getLogger(__name__)


class ScreenshotService:
    """Service for capturing and managing media screenshots."""

    def __init__(self, media_repository=None, screenshot_repository=None):
        self.media_repository = media_repository or get_media_repository()
        self.screenshot_repository = screenshot_repository or get_screenshot_repository()
        self._screenshots_dir = None

    async def _ensure_screenshots_dir(self) -> Path:
        """Ensure screenshots directory exists."""
        if not self._screenshots_dir:
            data_dir = await config_service.get('data_dir', '/tmp/giggityflix')
            self._screenshots_dir = Path(data_dir) / 'screenshots'
            self._screenshots_dir.mkdir(parents=True, exist_ok=True)
        return self._screenshots_dir

    async def capture_for_media(self, media_luid: str, quantity: int = 3) -> List[Screenshot]:
        """Capture screenshots for a media file."""
        media = self.media_repository.get_by_luid(media_luid)
        if not media or not media.exists():
            logger.error(f"Media file not found or doesn't exist: {media_luid}")
            return []

        try:
            screenshots_data = await self._extract_screenshots(media, quantity)
            screenshots = []

            screenshots_dir = await self._ensure_screenshots_dir()
            
            for i, (screenshot_data, timestamp) in enumerate(screenshots_data):
                screenshot_id = str(uuid.uuid4())
                filename = f"{media.luid}_{screenshot_id}.jpg"
                screenshot_path = screenshots_dir / filename

                # Save screenshot to disk
                with open(screenshot_path, 'wb') as f:
                    f.write(screenshot_data)

                # Create screenshot domain object
                screenshot = Screenshot(
                    id=screenshot_id,
                    media_luid=media.luid,
                    path=str(screenshot_path),
                    timestamp=timestamp,
                    width=media.width or 1920,
                    height=media.height or 1080
                )

                self.screenshot_repository.save(screenshot)
                screenshots.append(screenshot)

            logger.info(f"Captured {len(screenshots)} screenshots for {media_luid}")
            return screenshots

        except Exception as e:
            logger.error(f"Error capturing screenshots: {e}")
            return []

    async def upload_screenshots(self, screenshots: List[bytes], upload_endpoint: str, upload_token: str) -> bool:
        """Upload screenshots to remote endpoint."""
        if not screenshots:
            logger.warning("No screenshots to upload")
            return False

        try:
            headers = {"Authorization": f"Bearer {upload_token}"}
            form = aiohttp.FormData()

            for i, screenshot_data in enumerate(screenshots):
                form.add_field(
                    f"file{i}",
                    io.BytesIO(screenshot_data),
                    filename=f"screenshot_{i}.jpg",
                    content_type="image/jpeg"
                )

            async with aiohttp.ClientSession() as session:
                async with session.post(upload_endpoint, data=form, headers=headers) as response:
                    if response.status == 200:
                        logger.info(f"Successfully uploaded {len(screenshots)} screenshots")
                        return True
                    else:
                        logger.error(f"Error uploading screenshots: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Error uploading screenshots: {e}")
            return False

    @io_bound(param_name='media_path')
    async def _extract_screenshots(self, media: Media, quantity: int) -> List[tuple]:
        """Extract screenshot data and timestamps from media file."""
        video_path = str(media.path)
        video = cv2.VideoCapture(video_path)
        
        if not video.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        try:
            frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
            frame_rate = video.get(cv2.CAP_PROP_FPS)

            # Calculate frame positions
            frame_positions = FramePositionCalculator.calculate_frame_positions(
                start_frame=max(1, int(frames * 0.05)),
                usable_frames=int(frames * 0.9),
                quantity=quantity
            )

            quality_radius = FramePositionCalculator.calculate_quality_radius(
                frame_positions, frame_rate
            )

            screenshots_data = []
            for pos in frame_positions:
                start_pos, end_pos = FramePositionCalculator.get_valid_frame_range(
                    pos, quality_radius, frames
                )

                frames_data = []
                video.set(cv2.CAP_PROP_POS_FRAMES, start_pos)

                for _ in range(end_pos - start_pos + 1):
                    success, frame = video.read()
                    if not success or frame is None:
                        break

                    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    frames_data.append(buffer.tobytes())

                if frames_data:
                    # Find best quality frame
                    best_frame_data = await self._select_best_frame(frames_data)
                    timestamp = pos / frame_rate
                    screenshots_data.append((best_frame_data, timestamp))

            return screenshots_data

        finally:
            video.release()

    @cpu_bound()
    async def _select_best_frame(self, frames_data: List[bytes]) -> bytes:
        """Select the best quality frame from a list."""
        if len(frames_data) == 1:
            return frames_data[0]

        scores = [FrameQualityCalculator.calculate_quality_score(frame) for frame in frames_data]
        
        if any(s > 0 for s in scores):
            best_index = scores.index(max(scores))
            return frames_data[best_index]
        
        return frames_data[0]


# Singleton factory
_screenshot_service = None

def get_screenshot_service() -> ScreenshotService:
    """Get or create ScreenshotService instance."""
    global _screenshot_service
    if _screenshot_service is None:
        _screenshot_service = ScreenshotService()
    return _screenshot_service
