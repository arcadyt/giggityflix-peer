import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# Helper functions for parsing environment variables
def get_str_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

def get_int_env(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default

def get_bool_env(key: str, default: bool) -> bool:
    value = os.environ.get(key, str(default)).lower()
    return value == "true"

def get_str_list_env(key: str, default: str = "") -> List[str]:
    return [p.strip() for p in os.environ.get(key, default).split(",") if p.strip()]


# Default factory functions
def default_edge_address() -> str:
    return get_str_env("EDGE_GRPC_ADDRESS", "localhost:50051")

def default_reconnect_interval() -> int:
    return get_int_env("GRPC_RECONNECT_INTERVAL_SEC", 10)

def default_max_reconnect_attempts() -> int:
    return get_int_env("GRPC_MAX_RECONNECT_ATTEMPTS", 5)

def default_heartbeat_interval() -> int:
    return get_int_env("GRPC_HEARTBEAT_INTERVAL_SEC", 30)

def default_timeout_sec() -> int:
    return get_int_env("GRPC_TIMEOUT_SEC", 5)

def default_use_tls() -> bool:
    return get_bool_env("GRPC_USE_TLS", False)

def default_cert_path() -> Optional[str]:
    return get_str_env("GRPC_CERT_PATH", None)

def default_db_path() -> str:
    return get_str_env("DB_PATH", "peer.db")

def default_backup_dir() -> str:
    return get_str_env("DB_BACKUP_DIR", "backups")

def default_backup_interval() -> int:
    return get_int_env("DB_BACKUP_INTERVAL_HOURS", 24)

def default_media_dirs() -> List[str]:
    return get_str_list_env("MEDIA_DIRS")

def default_include_extensions() -> List[str]:
    return [ext.strip().lower() for ext in get_str_env("INCLUDE_EXTENSIONS", ".mp4,.mkv,.avi,.mov").split(",") if ext.strip()]

def default_exclude_dirs() -> List[str]:
    return get_str_list_env("EXCLUDE_DIRS")

def default_scan_interval() -> int:
    return get_int_env("SCAN_INTERVAL_MINUTES", 60)

def default_hash_algorithms() -> List[str]:
    return get_str_list_env("HASH_ALGORITHMS", "md5,sha1")

def default_extract_metadata() -> bool:
    return get_bool_env("EXTRACT_METADATA", True)

def default_log_level() -> str:
    return get_str_env("LOG_LEVEL", "INFO")

def default_log_dir() -> str:
    return get_str_env("LOG_DIR", "logs")

def default_max_size_mb() -> int:
    return get_int_env("LOG_MAX_SIZE_MB", 10)

def default_backup_count() -> int:
    return get_int_env("LOG_BACKUP_COUNT", 5)

def default_use_color() -> bool:
    return get_bool_env("LOG_USE_COLOR", True)

def default_stun_server() -> str:
    return get_str_env("STUN_SERVER", "stun:stun.l.google.com:19302")

def default_turn_server() -> str:
    return get_str_env("TURN_SERVER")

def default_turn_username() -> Optional[str]:
    return get_str_env("TURN_USERNAME", None)

def default_turn_password() -> Optional[str]:
    return get_str_env("TURN_PASSWORD", None)

def default_max_bandwidth() -> int:
    return get_int_env("WEBRTC_MAX_BANDWIDTH_KBPS", 5000)

def default_peer_id() -> str:
    return get_str_env("PEER_ID", "")

def default_auto_generate_id() -> bool:
    return get_bool_env("AUTO_GENERATE_ID", True)

def default_data_dir() -> str:
    return get_str_env("DATA_DIR", str(Path.home() / ".giggityflix_peer"))

def default_screenshot_cache_size() -> int:
    return get_int_env("SCREENSHOT_CACHE_SIZE_MB", 100)

def default_http_port() -> int:
    return get_int_env("HTTP_PORT", 8080)

def default_enable_upnp() -> bool:
    return get_bool_env("ENABLE_UPNP", True)


class GrpcConfig(BaseModel):
    """gRPC client configuration."""
    edge_address: str = Field(default_factory=default_edge_address)
    reconnect_interval_sec: int = Field(default_factory=default_reconnect_interval)
    max_reconnect_attempts: int = Field(default_factory=default_max_reconnect_attempts)
    heartbeat_interval_sec: int = Field(default_factory=default_heartbeat_interval)
    timeout_sec: int = Field(default_factory=default_timeout_sec)
    use_tls: bool = Field(default_factory=default_use_tls)
    cert_path: Optional[str] = Field(default_factory=default_cert_path)


class DbConfig(BaseModel):
    """SQLite database configuration."""
    path: str = Field(default_factory=default_db_path)
    backup_dir: str = Field(default_factory=default_backup_dir)
    backup_interval_hours: int = Field(default_factory=default_backup_interval)


class ScannerConfig(BaseModel):
    """Media scanner configuration."""
    media_dirs: List[str] = Field(default_factory=default_media_dirs)
    include_extensions: List[str] = Field(default_factory=default_include_extensions)
    exclude_dirs: List[str] = Field(default_factory=default_exclude_dirs)
    scan_interval_minutes: int = Field(default_factory=default_scan_interval)
    hash_algorithms: List[str] = Field(default_factory=default_hash_algorithms)
    extract_metadata: bool = Field(default_factory=default_extract_metadata)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default_factory=default_log_level)
    log_dir: str = Field(default_factory=default_log_dir)
    max_size_mb: int = Field(default_factory=default_max_size_mb)
    backup_count: int = Field(default_factory=default_backup_count)
    use_color: bool = Field(default_factory=default_use_color)


class WebRtcConfig(BaseModel):
    """WebRTC configuration."""
    stun_server: str = Field(default_factory=default_stun_server)
    turn_server: str = Field(default_factory=default_turn_server)
    turn_username: Optional[str] = Field(default_factory=default_turn_username)
    turn_password: Optional[str] = Field(default_factory=default_turn_password)
    max_bandwidth_kbps: int = Field(default_factory=default_max_bandwidth)


class PeerConfig(BaseModel):
    """Peer service configuration."""
    peer_id: str = Field(default_factory=default_peer_id)
    auto_generate_id: bool = Field(default_factory=default_auto_generate_id)
    data_dir: str = Field(default_factory=default_data_dir)
    screenshot_cache_size_mb: int = Field(default_factory=default_screenshot_cache_size)
    http_port: int = Field(default_factory=default_http_port)
    enable_upnp: bool = Field(default_factory=default_enable_upnp)


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