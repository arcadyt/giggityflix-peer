import os
from unittest import mock

from giggityflix_peer.config import AppConfig


def test_default_config():
    """Test that the default configuration loads correctly."""
    config = AppConfig()

    # Check that all sections exist
    assert hasattr(config, "grpc")
    assert hasattr(config, "db")
    assert hasattr(config, "scanner")
    assert hasattr(config, "logging")
    assert hasattr(config, "webrtc")
    assert hasattr(config, "peer")

    # Check some default values
    assert config.grpc.edge_address == "localhost:50051"
    assert config.grpc.reconnect_interval_sec == 10
    assert config.db.path == "peer.db"
    assert config.webrtc.max_bandwidth_kbps == 5000


def test_environment_variables():
    """Test that environment variables override default configuration."""
    with mock.patch.dict(os.environ, {
        "EDGE_GRPC_ADDRESS": "test.example.com:50051",
        "GRPC_RECONNECT_INTERVAL_SEC": "20",
        "DB_PATH": "test.db",
        "MEDIA_DIRS": "/path/to/media1,/path/to/media2",
        "INCLUDE_EXTENSIONS": ".mp4,.mkv",
        "PEER_ID": "test-peer-id"
    }):
        config = AppConfig()

        # Check that environment variables were applied
        assert config.grpc.edge_address == "test.example.com:50051"
        assert config.grpc.reconnect_interval_sec == 20
        assert config.db.path == "test.db"
        assert config.scanner.media_dirs == ["/path/to/media1", "/path/to/media2"]
        assert config.scanner.include_extensions == [".mp4", ".mkv"]
        assert config.peer.peer_id == "test-peer-id"


def test_media_dirs_parsing():
    """Test that media directories are parsed correctly."""
    with mock.patch.dict(os.environ, {
        "MEDIA_DIRS": "/path/with spaces/movies,/another path/tv shows"
    }):
        config = AppConfig()

        # Check that paths with spaces are handled correctly
        assert config.scanner.media_dirs == ["/path/with spaces/movies", "/another path/tv shows"]


def test_empty_media_dirs():
    """Test that empty media directories result in an empty list."""
    with mock.patch.dict(os.environ, {
        "MEDIA_DIRS": ""
    }):
        config = AppConfig()

        # Check that empty media dirs results in an empty list
        assert config.scanner.media_dirs == []


def test_boolean_parsing():
    """Test that boolean values are parsed correctly."""
    with mock.patch.dict(os.environ, {
        "GRPC_USE_TLS": "true",
        "EXTRACT_METADATA": "false",
        "AUTO_GENERATE_ID": "0"
    }):
        config = AppConfig()

        # Check that boolean values are parsed correctly
        assert config.grpc.use_tls is True
        assert config.scanner.extract_metadata is False
        assert config.peer.auto_generate_id is False
