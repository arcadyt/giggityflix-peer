import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GrpcConfig(BaseModel):
    """gRPC client configuration."""
    edge_address: str = Field(default_factory=lambda: os.environ.get("EDGE_GRPC_ADDRESS", "localhost:50051"))
    reconnect_interval_sec: int = Field(default_factory=lambda: int(os.environ.get("GRPC_RECONNECT_INTERVAL_SEC", "10")))
    max_reconnect_attempts: int = Field(default_factory=lambda: int(os.environ.get("GRPC_MAX_RECONNECT_ATTEMPTS", "5")))
    heartbeat_interval_sec: int = Field(default_factory=lambda: int(os.environ.get("GRPC_HEARTBEAT_INTERVAL_SEC", "30")))
    timeout_sec: int = Field(default_factory=lambda: int(os.environ.get("GRPC_TIMEOUT_SEC", "5")))
    use_tls: bool = Field(default_factory=lambda: os.environ.get("GRPC_USE_TLS", "false").lower() == "true")
    cert_path: Optional[str] = Field(default_factory=lambda: os.environ.get("GRPC_CERT_PATH"))


class DbConfig(BaseModel):
    """SQLite database configuration."""
    path: str = Field(default_factory=lambda: os.environ.get("DB_PATH", "peer.db"))
    backup_dir: str = Field(default_factory=lambda: os.environ.get("DB_BACKUP_DIR", "backups"))
    backup_interval_hours: int = Field(default_factory=lambda: int(os.environ.get("DB_BACKUP_INTERVAL_HOURS", "24")))


class ScannerConfig(BaseModel):
    """Media scanner configuration."""
    media_dirs: List[str] = Field(default_factory=lambda: [p.strip() for p in os.environ.get("MEDIA_DIRS", "").split(",") if p.strip()])
    include_extensions: List[str] = Field(default_factory=lambda: [ext.strip().lower() for ext in os.environ.get("INCLUDE_EXTENSIONS", ".mp4,.mkv,.avi,.mov").split(",") if ext.strip()])
    exclude_dirs: List[str] = Field(default_factory=lambda: [p.strip() for p in os.environ.get("EXCLUDE_DIRS", "").split(",") if p.strip()])
    scan_interval_minutes: int = Field(default_factory=lambda: int(os.environ.get("SCAN_INTERVAL_MINUTES", "60")))
    hash_algorithms: List[str] = Field(default_factory=lambda: [algo.strip() for algo in os.environ.get("HASH_ALGORITHMS", "md5,sha1").split(",") if algo.strip()])
    extract_metadata: bool = Field(default_factory=lambda: os.environ.get("EXTRACT_METADATA", "true").lower() == "true")


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    log_dir: str = Field(default_factory=lambda: os.environ.get("LOG_DIR", "logs"))
    max_size_mb: int = Field(default_factory=lambda: int(os.environ.get("LOG_MAX_SIZE_MB", "10")))
    backup_count: int = Field(default_factory=lambda: int(os.environ.get("LOG_BACKUP_COUNT", "5")))
    use_color: bool = Field(default_factory=lambda: os.environ.get("LOG_USE_COLOR", "true").lower() == "true")


class WebRtcConfig(BaseModel):
    """WebRTC configuration."""
    stun_servers: List[str] = Field(default_factory=lambda: [s.strip() for s in os.environ.get("STUN_SERVERS", "stun:stun.l.google.com:19302").split(",") if s.strip()])
    turn_servers: List[str] = Field(default_factory=lambda: [s.strip() for s in os.environ.get("TURN_SERVERS", "").split(",") if s.strip()])
    turn_username: Optional[str] = Field(default_factory=lambda: os.environ.get("TURN_USERNAME"))
    turn_password: Optional[str] = Field(default_factory=lambda: os.environ.get("TURN_PASSWORD"))
    max_bandwidth_kbps: int = Field(default_factory=lambda: int(os.environ.get("WEBRTC_MAX_BANDWIDTH_KBPS", "5000")))


class PeerConfig(BaseModel):
    """Peer service configuration."""
    peer_id: str = Field(default_factory=lambda: os.environ.get("PEER_ID", ""))
    auto_generate_id: bool = Field(default_factory=lambda: os.environ.get("AUTO_GENERATE_ID", "true").lower() == "true")
    data_dir: str = Field(default_factory=lambda: os.environ.get("DATA_DIR", str(Path.home() / ".giggityflix_peer")))
    screenshot_cache_size_mb: int = Field(default_factory=lambda: int(os.environ.get("SCREENSHOT_CACHE_SIZE_MB", "100")))
    http_port: int = Field(default_factory=lambda: int(os.environ.get("HTTP_PORT", "8080")))
    enable_upnp: bool = Field(default_factory=lambda: os.environ.get("ENABLE_UPNP", "true").lower() == "true")


class AppConfig(BaseModel):
    """Application configuration."""
    grpc: GrpcConfig = Field(default_factory=GrpcConfig)
    db: DbConfig = Field(default_factory=DbConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    webrtc: WebRtcConfig = Field(default_factory=WebRtcConfig)
    peer: PeerConfig = Field(default_factory=PeerConfig)


# Create a singleton config instance
config = AppConfig()
