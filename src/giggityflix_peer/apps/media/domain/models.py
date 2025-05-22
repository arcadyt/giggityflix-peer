"""Domain models for media entities."""
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class MediaType(str, Enum):
    """Types of media files."""
    VIDEO = "video"
    AUDIO = "audio"
    UNSUPPORTED = "unsupported"

class MediaStatus(str, Enum):
    """Status of a media file in the system."""
    PENDING = "pending"  # File found but not yet processed
    PROCESSING = "processing"  # Currently being processed
    READY = "ready"  # Processed and ready for streaming
    ERROR = "error"  # Error occurred during processing
    DELETED = "deleted"  # File no longer exists


class Media:
    """Domain model for a media file."""
    
    def __init__(self, 
                 luid: str,
                 path: str,
                 size_bytes: int,
                 media_type: MediaType,
                 status: MediaStatus = MediaStatus.PENDING,
                 catalog_id: Optional[str] = None,
                 relative_path: Optional[str] = None,
                 duration_seconds: Optional[float] = None,
                 width: Optional[int] = None,
                 height: Optional[int] = None,
                 codec: Optional[str] = None,
                 bitrate: Optional[int] = None,
                 framerate: Optional[float] = None,
                 hashes: Optional[Dict[str, str]] = None,
                 view_count: int = 0,
                 created_at: Optional[datetime] = None,
                 modified_at: Optional[datetime] = None,
                 last_accessed: Optional[datetime] = None,
                 last_viewed: Optional[datetime] = None,
                 error_message: Optional[str] = None):
        """Initialize a Media domain object."""
        self.luid = luid
        self.path = path
        self.relative_path = relative_path
        self.size_bytes = size_bytes
        self.media_type = media_type
        self.status = status
        self.catalog_id = catalog_id
        
        # Media metadata
        self.duration_seconds = duration_seconds
        self.width = width
        self.height = height
        self.codec = codec
        self.bitrate = bitrate
        self.framerate = framerate
        
        # File metadata
        self.created_at = created_at or datetime.now()
        self.modified_at = modified_at
        self.last_accessed = last_accessed
        
        # Stream metadata
        self.view_count = view_count
        self.last_viewed = last_viewed
        
        # Hashes for verification
        self.hashes = hashes or {}
        
        # Error information
        self.error_message = error_message
        
    def get_path_object(self) -> Path:
        """Get path as a Path object."""
        return Path(self.path)
    
    def increment_view_count(self) -> None:
        """Increment the view count and update last_viewed."""
        self.view_count += 1
        self.last_viewed = datetime.now()
        
    def mark_deleted(self) -> None:
        """Mark the media as deleted."""
        self.status = MediaStatus.DELETED
        
    def exists(self) -> bool:
        """Check if the file exists on disk."""
        return Path(self.path).exists()


class Screenshot:
    """Domain model for a media screenshot."""
    
    def __init__(self,
                 id: str,
                 media_luid: str,
                 path: str,
                 timestamp: float,
                 width: int,
                 height: int,
                 created_at: Optional[datetime] = None):
        """Initialize a Screenshot domain object."""
        self.id = id
        self.media_luid = media_luid
        self.path = path
        self.timestamp = timestamp
        self.width = width
        self.height = height
        self.created_at = created_at or datetime.now()
    
    def get_path_object(self) -> Path:
        """Get path as a Path object."""
        return Path(self.path)
