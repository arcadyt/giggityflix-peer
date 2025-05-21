import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional

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


class VideoReader:
    """Handles video file reading operations"""

    @staticmethod
    def get_property(video: cv2.VideoCapture, prop_id, default=None):
        """Get property value from video capture object"""
        value = video.get(prop_id)
        return value if value > 0 else default

    @staticmethod
    def extract_metadata(video_path: str) -> Optional[VideoMetadata]:
        """Extract metadata from video file"""
        try:
            video = cv2.VideoCapture(video_path)
            if not video.isOpened():
                logger.error(f"Could not open video file: {video_path}")
                return None

            try:
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
            finally:
                video.release()
        except Exception as e:
            logger.error(f"Error extracting metadata from {video_path}: {e}")
            return None

    @staticmethod
    def _decode_fourcc(fourcc_int: int) -> Optional[str]:
        """Decode FourCC codec identifier"""
        if fourcc_int == 0:
            return None

        try:
            return fourcc_int.to_bytes(4, 'little').decode('ascii').strip('\0')
        except (ValueError, UnicodeDecodeError):
            return f"codec-{fourcc_int}"


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
