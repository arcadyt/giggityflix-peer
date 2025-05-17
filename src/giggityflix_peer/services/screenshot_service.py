import io
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List

import aiohttp
import cv2

from giggityflix_peer.services.disk_io_service import disk_io_service
from giggityflix_peer.utils.video_file_utils import FramePositionCalculator, FrameQualityCalculator

logger = logging.getLogger(__name__)


class ScreenshotUploader:
    """Handles screenshot upload operations"""

    @staticmethod
    async def upload_screenshots(screenshots: List[bytes], upload_endpoint: str, upload_token: str) -> bool:
        """Upload screenshots to remote endpoint"""
        if not screenshots:
            logger.warning("No screenshots to upload")
            return False

        try:
            headers = {"Authorization": f"Bearer {upload_token}"}

            # Create a single form with all files
            form = aiohttp.FormData()
            for i, screenshot_data in enumerate(screenshots):
                form.add_field(
                    f"file{i}",  # Unique field name for each file
                    io.BytesIO(screenshot_data),
                    filename=f"screenshot_{i}.jpg",
                    content_type="image/jpeg"
                )

            # Send a single HTTP request with all files
            async with aiohttp.ClientSession() as session:
                async with session.post(upload_endpoint, data=form, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Error uploading screenshots: {response.status}")
                        return False

                    logger.info(f"Successfully uploaded {len(screenshots)} screenshots in one request")
                    return True

        except Exception as e:
            logger.error(f"Error uploading screenshots: {e}", exc_info=True)
            return False


class ScreenshotService:
    """Service for capturing screenshots from video files"""

    def __init__(self, max_workers: int = 16):
        self.max_workers = max_workers
        self._process_pool = ProcessPoolExecutor(max_workers=self.max_workers)

    async def capture_screenshots(self, file_path: str, quantity: int = 1) -> List[bytes]:
        """Capture optimized screenshots from video file"""
        path = Path(file_path)
        logger.info(f"Capturing {quantity} screenshots from: {path}")

        if not path.is_file():
            logger.error(f"File does not exist: {path}")
            raise FileNotFoundError(f"File not found: {path}")

        # Use disk I/O service to limit concurrent operations on the same drive
        async with disk_io_service.operation(str(path)):
            try:
                video = cv2.VideoCapture(str(path))
                if not video.isOpened():
                    raise ValueError(f"Could not open video file: {path}")

                try:
                    # Get basic video properties directly
                    frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
                    frame_rate = video.get(cv2.CAP_PROP_FPS)

                    if frames <= 0:
                        logger.warning(f"Frame count unavailable: {path}")
                        return []

                    # Calculate frame positions
                    frame_positions = FramePositionCalculator.calculate_frame_positions(
                        start_frame=max(1, int(frames * 0.05)),
                        usable_frames=int(frames * 0.9),
                        quantity=quantity
                    )

                    quality_radius = FramePositionCalculator.calculate_quality_radius(
                        frame_positions, frame_rate
                    )

                    # Capture the screenshots
                    screenshots = self._capture_best_frames(video, frame_positions, quality_radius, frames)

                    logger.info(f"Captured {len(screenshots)} screenshots")
                    return screenshots

                finally:
                    video.release()

            except Exception as e:
                logger.error(f"Error capturing screenshots: {e}", exc_info=True)
                raise

    def _capture_best_frames(self, video: cv2.VideoCapture, positions: List[int],
                             quality_radius: int, total_frames: int) -> List[bytes]:
        """Capture the best quality frame around each target position"""

        screenshots = []

        for frame_pos in positions:
            start_pos, end_pos = FramePositionCalculator.get_valid_frame_range(
                frame_pos, quality_radius, total_frames
            )

            if start_pos >= end_pos:
                logger.warning(f"Invalid frame range at position {frame_pos}")
                continue

            video.set(cv2.CAP_PROP_POS_FRAMES, start_pos)

            frame_jpgs = []
            for _ in range(end_pos - start_pos + 1):
                success, frame = video.read()
                if not success or frame is None:
                    break

                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                frame_jpgs.append(buffer.tobytes())

            if not frame_jpgs:
                continue

            try:
                scores = list(self._process_pool.map(
                    FrameQualityCalculator.calculate_quality_score, frame_jpgs
                ))
                best_index = scores.index(max(scores)) if any(s > 0 for s in scores) else 0
                screenshots.append(frame_jpgs[best_index])
            except Exception as e:
                logger.error(f"Error processing quality: {e}")
                if frame_jpgs:
                    screenshots.append(frame_jpgs[0])

        return screenshots


# Singleton instance
screenshot_service = ScreenshotService()
