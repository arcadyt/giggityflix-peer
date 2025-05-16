import io
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional

import aiohttp
import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VideoMetadata:
    """Video file metadata container"""
    height: int
    width: int
    frame_rate: float
    codec: str
    frames: int
    bit_rate: int


class FrameQualityCalculator:
    """Calculates quality metrics for video frames"""

    @staticmethod
    def calculate_quality_score(frame_data: bytes) -> float:
        """Calculate Laplacian variance score for a frame"""
        np_array = np.frombuffer(frame_data, dtype=np.uint8)
        frame = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        if frame is None:
            return -1

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.Laplacian(gray, cv2.CV_64F).var()


class VideoReader:
    """Handles video file reading operations"""

    @staticmethod
    def get_property(video: cv2.VideoCapture, prop_id, default=None):
        """Get property value from video capture object"""
        value = video.get(prop_id)
        return value if value > 0 else default

    @staticmethod
    def extract_metadata(video: cv2.VideoCapture) -> VideoMetadata:
        """Extract metadata from video file"""
        fourcc_int = int(VideoReader.get_property(video, cv2.CAP_PROP_FOURCC))
        codec = VideoReader._decode_fourcc(fourcc_int)

        return VideoMetadata(
            height=int(VideoReader.get_property(video, cv2.CAP_PROP_FRAME_HEIGHT)),
            width=int(VideoReader.get_property(video, cv2.CAP_PROP_FRAME_WIDTH)),
            frame_rate=VideoReader.get_property(video, cv2.CAP_PROP_FPS),
            codec=codec,
            frames=int(VideoReader.get_property(video, cv2.CAP_PROP_FRAME_COUNT)),
            bit_rate=int(VideoReader.get_property(video, cv2.CAP_PROP_BITRATE))
        )

    @staticmethod
    def _decode_fourcc(fourcc_int: int) -> Optional[str]:
        """Decode FourCC codec identifier"""
        if fourcc_int == 0:
            return None

        try:
            return fourcc_int.to_bytes(4, 'little').decode('ascii').strip('\0')
        except (ValueError, UnicodeDecodeError):
            return f"codec-{fourcc_int}"


class FramePositionCalculator:
    """Calculates optimal frame positions for extraction"""

    @staticmethod
    def calculate_frame_positions(start_frame: int, usable_frames: int, quantity: int) -> List[int]:
        """Calculate evenly distributed frame positions"""
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
        """Determine optimal search radius based on positions and frame rate"""
        distances = [positions[i + 1] - positions[i] for i in range(len(positions) - 1)] if len(positions) > 1 else []
        min_distance = min(distances) if distances else float('inf')

        return min(int(frame_rate), min_distance // 2) if min_distance != float('inf') else int(frame_rate)

    @staticmethod
    def get_valid_frame_range(target_pos: int, radius: int, total_frames: int) -> Tuple[int, int]:
        """Calculate valid frame range within video bounds"""
        start_pos = max(0, target_pos - radius)
        end_pos = min(total_frames - 1, target_pos + radius)
        return start_pos, end_pos


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
            uploaded_count = 0

            async with aiohttp.ClientSession() as session:
                for i, screenshot_data in enumerate(screenshots):
                    form = aiohttp.FormData()
                    form.add_field(
                        "file",
                        io.BytesIO(screenshot_data),
                        filename=f"screenshot_{i}.jpg",
                        content_type="image/jpeg"
                    )

                    async with session.post(upload_endpoint, data=form, headers=headers) as response:
                        if response.status != 200:
                            logger.error(f"Error uploading screenshot {i}: {response.status}")
                            continue

                        uploaded_count += 1
                        logger.info(f"Uploaded screenshot {i} ({len(screenshot_data)} bytes)")

            return uploaded_count > 0

        except Exception as e:
            logger.error(f"Error uploading screenshots: {e}", exc_info=True)
            return False


class ScreenshotService:
    """Service for capturing better-quality screenshots from video files"""

    def __init__(self, max_workers: int = 16):
        self.max_workers = max_workers
        self._process_pool = ProcessPoolExecutor(max_workers=self.max_workers)
        self._frame_quality_calculator = FrameQualityCalculator()

    async def capture_screenshots(self, file_path: str, quantity: int = 1) -> Tuple[List[bytes], VideoMetadata]:
        """Capture optimized screenshots from video file"""
        path = Path(file_path)
        logger.info(f"Capturing {quantity} screenshots from: {path}")

        if not path.is_file():
            logger.error(f"File does not exist: {path}")
            raise FileNotFoundError(f"File not found: {path}")

        try:
            video = cv2.VideoCapture(str(path))
            if not video.isOpened():
                raise ValueError(f"Could not open video file: {path}")

            try:
                metadata = VideoReader.extract_metadata(video)
                logger.debug(f"Video metadata: {metadata}")

                if metadata.frames <= 0:
                    logger.warning(f"Frame count unavailable: {path}")
                    return [], metadata

                frame_positions = FramePositionCalculator.calculate_frame_positions(
                    start_frame=max(1, int(metadata.frames * 0.05)),
                    usable_frames=int(metadata.frames * 0.9),
                    quantity=quantity
                )

                quality_radius = FramePositionCalculator.calculate_quality_radius(
                    frame_positions, metadata.frame_rate
                )
                screenshots = self._capture_best_frames(video, frame_positions, quality_radius, metadata.frames)

                logger.info(f"Captured {len(screenshots)} screenshots")
                return screenshots, metadata
            finally:
                video.release()

        except Exception as e:
            logger.error(f"Error capturing screenshots: {e}", exc_info=True)
            raise

    def _capture_best_frames(self, video: cv2.VideoCapture, positions: List[int],
                             quality_radius: int, total_frames: int) -> List[bytes]:
        """Capture best quality frame around each target position"""
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
