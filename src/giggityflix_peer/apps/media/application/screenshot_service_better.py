import io
import logging
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List, Optional, Tuple

import aiohttp
import cv2
import numpy as np

from giggityflix_peer.models.media import MediaFile
from giggityflix_peer.old_resource_mgmt.annotations import io_bound, cpu_bound
from giggityflix_peer.old_utils.video_file_utils import FramePositionCalculator, FrameQualityCalculator

logger = logging.getLogger(__name__)


class ScreenshotCapture:
    """Handles the screenshot capture process"""

    @io_bound(param_name='video_path')
    def extract_frames(self, video_path: str, positions: List[Tuple[int, int]]) -> List[np.ndarray]:
        """
        Extract frames from a video file in one IO operation.

        Args:
            video_path: Path to the video file
            positions: List of (start_pos, end_pos) for frame ranges to extract

        Returns:
            List of extracted frames as numpy arrays
        """
        video = cv2.VideoCapture(video_path)
        if not video.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        try:
            all_frames = []

            for start_pos, end_pos in positions:
                frames_for_position = []
                video.set(cv2.CAP_PROP_POS_FRAMES, start_pos)

                for _ in range(end_pos - start_pos + 1):
                    success, frame = video.read()
                    if not success or frame is None:
                        break
                    frames_for_position.append(frame)

                all_frames.append(frames_for_position)

            return all_frames
        finally:
            video.release()

    @staticmethod
    def frames_to_jpeg(frames: List[np.ndarray]) -> List[bytes]:
        """Convert frames to JPEG bytes"""
        jpeg_frames = []
        for frame in frames:
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            jpeg_frames.append(buffer.tobytes())
        return jpeg_frames

    @cpu_bound()
    def calculate_frame_qualities(self, frame_jpgs: List[bytes]) -> List[float]:
        """Calculate quality scores for a batch of frames"""
        return [FrameQualityCalculator.calculate_quality_score(frame) for frame in frame_jpgs]


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

    def __init__(self):
        self.screenshot_capture = ScreenshotCapture()

    async def capture_screenshots(self, media_file: MediaFile, quantity: int = 1) -> List[bytes]:
        """Capture optimized screenshots from a media file"""
        file_path = str(media_file.path)
        logger.info(f"Capturing {quantity} screenshots from: {file_path}")

        if not Path(file_path).is_file():
            logger.error(f"File does not exist: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Open video just to get properties (metadata should be cached in future)
            video = cv2.VideoCapture(file_path)
            if not video.isOpened():
                raise ValueError(f"Could not open video file: {file_path}")

            try:
                # Get video properties
                frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
                frame_rate = video.get(cv2.CAP_PROP_FPS)

                position_ranges = await self._calculate_position_ranges(frame_rate, frames, quantity)

                if not position_ranges:
                    logger.warning("No valid frame ranges found")
                    return []

                # Extract all frames in one IO operation
                all_frame_groups = await self.screenshot_capture.extract_frames(file_path, position_ranges)

                # Process each position's frames
                screenshots = []
                for frames_group in all_frame_groups:
                    if not frames_group:
                        continue

                    # Convert frames to JPEG
                    jpeg_frames = self.screenshot_capture.frames_to_jpeg(frames_group)

                    if not jpeg_frames:
                        continue

                    try:
                        # Calculate quality scores - CPU bound
                        scores = await self.screenshot_capture.calculate_frame_qualities(jpeg_frames)

                        # Select best frame - single threaded, don't touch
                        if any(s > 0 for s in scores):
                            best_index = scores.index(max(scores))
                            screenshots.append(jpeg_frames[best_index])
                        else:
                            screenshots.append(jpeg_frames[0])
                    except Exception as e:
                        logger.error(f"Error processing quality: {e}")
                        if jpeg_frames:
                            screenshots.append(jpeg_frames[0])

                logger.info(f"Captured {len(screenshots)} screenshots")
                return screenshots

            finally:
                video.release()

        except Exception as e:
            logger.error(f"Error capturing screenshots: {e}", exc_info=True)
            raise

    async def _calculate_position_ranges(self, frame_rate, frames, quantity):
        # Calculate frame positions - single threaded, don't touch
        frame_positions = FramePositionCalculator.calculate_frame_positions(
            start_frame=max(1, int(frames * 0.05)),
            usable_frames=int(frames * 0.9),
            quantity=quantity
        )
        quality_radius = FramePositionCalculator.calculate_quality_radius(
            frame_positions, frame_rate
        )
        # Prepare position ranges for extraction
        position_ranges = []
        for pos in frame_positions:
            start_pos, end_pos = FramePositionCalculator.get_valid_frame_range(
                pos, quality_radius, frames
            )
            if start_pos < end_pos:
                position_ranges.append((start_pos, end_pos))
        return position_ranges


# Singleton instance
screenshot_service = ScreenshotService()