# Giggityflix Peer Service

Peer-side component for the Giggityflix media streaming platform, enabling local media discovery and streaming.

## Overview

The Peer Service is a key component of the Giggityflix media streaming platform, designed to:

- Scan the local filesystem for media files
- Maintain a local database of available media
- Communicate with the Edge Service via gRPC
- Stream video using WebRTC
- Capture screenshots of media for preview
- Handle requests from Edge Service for media operations

## Prerequisites

- Python 3.11 or higher
- Poetry (for dependency management)
- Access to a Giggityflix Edge Service
- FFmpeg (optional, for enhanced video processing)
- OpenCV (optional, for enhanced screenshot capabilities)

## Installation

```bash
# Clone the repository
git clone https://github.com/giggityflix/giggityflix-peer.git
cd giggityflix_peer-peer

# Install dependencies
poetry install

# Install optional dependencies for enhanced video processing
poetry install -E video
```

## Configuration

The Peer Service can be configured using environment variables or command-line arguments:

### Media Configuration

- `MEDIA_DIRS`: Comma-separated list of directories to scan for media files
- `INCLUDE_EXTENSIONS`: Comma-separated list of file extensions to include (default: .mp4,.mkv,.avi,.mov)
- `EXCLUDE_DIRS`: Comma-separated list of directories to exclude from scanning
- `SCAN_INTERVAL_MINUTES`: Interval between automatic scans (default: 60)
- `HASH_ALGORITHMS`: Comma-separated list of hash algorithms to use (default: md5,sha1)
- `EXTRACT_METADATA`: Whether to extract metadata from media files (default: true)

### Network Configuration

- `EDGE_GRPC_ADDRESS`: Address of the Edge Service (default: localhost:50051)
- `GRPC_RECONNECT_INTERVAL_SEC`: Interval between reconnection attempts (default: 10)
- `GRPC_MAX_RECONNECT_ATTEMPTS`: Maximum number of reconnection attempts (default: 5)
- `GRPC_HEARTBEAT_INTERVAL_SEC`: Interval between heartbeats (default: 30)
- `GRPC_TIMEOUT_SEC`: Timeout for gRPC requests (default: 5)
- `GRPC_USE_TLS`: Whether to use TLS for gRPC (default: false)
- `GRPC_CERT_PATH`: Path to TLS certificate

### Peer Configuration

- `PEER_ID`: Unique identifier for this peer (auto-generated if not provided)
- `AUTO_GENERATE_ID`: Whether to auto-generate a peer ID (default: true)
- `DATA_DIR`: Directory for peer data (default: ~/.giggityflix)
- `SCREENSHOT_CACHE_SIZE_MB`: Size of the screenshot cache (default: 100)
- `HTTP_PORT`: Port for the HTTP server (default: 8080)
- `ENABLE_UPNP`: Whether to enable UPnP for port forwarding (default: true)

### WebRTC Configuration

- `STUN_SERVERS`: Comma-separated list of STUN servers (default: stun:stun.l.google.com:19302)
- `TURN_SERVERS`: Comma-separated list of TURN servers
- `TURN_USERNAME`: Username for TURN servers
- `TURN_PASSWORD`: Password for TURN servers
- `WEBRTC_MAX_BANDWIDTH_KBPS`: Maximum bandwidth for WebRTC (default: 5000)

## Usage

### Starting the Service

```bash
# Start with default configuration
poetry run python -m src.main start

# Start with custom media directory
poetry run python -m src.main start --media-dir /path/to/movies --media-dir /path/to/tv

# Start with custom edge address
poetry run python -m src.main start --edge-address edge.example.com:50051

# Start with custom peer ID
poetry run python -m src.main start --peer-id my-custom-peer-id
```

### Triggering a Media Scan

```bash
# Trigger a media scan
poetry run python -m src.main scan
```

### Checking Status

```bash
# Check the status of the peer service
poetry run python -m src.main status
```

## Architecture

The Peer Service consists of several key components:

- **Media Scanner**: Scans directories for media files and monitors for changes
- **Database Service**: Manages the local SQLite database of media files
- **Edge Client**: Communicates with the Edge Service via gRPC
- **Screenshot Service**: Captures screenshots from media files
- **Streaming Service**: Handles WebRTC streaming (to be implemented)

## Development

### Setting Up a Development Environment

```bash
# Clone the repository
git clone https://github.com/giggityflix/giggityflix-peer.git
cd giggityflix_peer-peer

# Install dependencies including development tools
poetry install --with dev

# Run tests
poetry run pytest
```

### Project Structure

```
giggityflix-peer/
├── src/
│   ├── config.py           # Configuration handling
│   ├── main.py             # CLI entry point
│   ├── peer_app.py         # Main application
│   ├── db/                 # Database layer
│   ├── models/             # Data models
│   ├── scanner/            # Media scanning
│   ├── services/           # Business logic
│   └── utils/              # Utilities
├── tests/                  # Test suite
├── pyproject.toml          # Project metadata and dependencies
└── README.md               # This file
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
