from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MediaType(str, Enum):
    """Types of media files."""
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    UNKNOWN = "unknown"


class MediaStatus(str, Enum):
    """Status of a media file in the system."""
    PENDING = "pending"     # File found but not yet processed
    PROCESSING = "processing"   # Currently being processed
    READY = "ready"         # Processed and ready for streaming
    ERROR = "error"         # Error occurred during processing
    DELETED = "deleted"     # File no longer exists


class MediaFile(BaseModel):
    """Represents a media file on the local filesystem."""
    luid: str  # Local unique identifier
    catalog_id: Optional[str] = None  # Assigned by the catalog service
    path: Path  # Absolute path to the file
    relative_path: Optional[str] = None  # Path relative to the media directory
    size_bytes: int
    media_type: MediaType
    status: MediaStatus = MediaStatus.PENDING
    
    # File metadata
    created_at: datetime = Field(default_factory=datetime.now)
    modified_at: Optional[datetime] = None
    last_accessed: Optional[datetime] = None
    
    # Media metadata
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    framerate: Optional[float] = None
    
    # Hashes for verification
    hashes: Dict[str, str] = Field(default_factory=dict)
    
    # Streaming stats
    view_count: int = 0
    last_viewed: Optional[datetime] = None
    
    # Screenshots
    screenshot_timestamps: List[float] = Field(default_factory=list)
    
    # Error information
    error_message: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True


class MediaCollection(BaseModel):
    """Represents a collection of related media files (e.g., a TV series)."""
    id: str
    name: str
    media_type: MediaType
    files: List[str] = Field(default_factory=list)  # List of LUIDs
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
    modified_at: Optional[datetime] = None


class Screenshot(BaseModel):
    """Represents a screenshot of a media file."""
    id: str
    media_luid: str
    timestamp: float  # Timestamp in seconds from the start of the media
    path: Path
    width: int
    height: int
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        arbitrary_types_allowed = True
