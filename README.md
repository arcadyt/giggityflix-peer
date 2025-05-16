# Giggityflix Peer Service

Peer-side component for the Giggityflix media streaming platform, enabling local media discovery and streaming.

## Overview

The Peer Service discovers and shares local media files with the Giggityflix platform:

- Scans local filesystem for media files
- Communicates with Edge Service via gRPC
- Maintains local database of available media
- Captures screenshots of media for preview
- Streams video using WebRTC
- Responds to file operation requests

## Architecture

### Components

- **Edge Client**: Manages gRPC connection to Edge Service
- **Media Scanner**: Scans directories for media files
- **Database Service**: Stores media metadata and state
- **Screenshot Service**: Captures and uploads media previews
- **Stream Service**: Handles WebRTC media streaming
- **Message Handlers**: Process incoming edge commands

### Connection Flow

1. **Edge Connection**:
   - Establishes gRPC connection with Edge Service
   - Provides peer_id in connection metadata
   - Opens bidirectional stream for message exchange
   - Sends initial catalog announcement

2. **Message Handling**:
   - Receives commands from Edge Service (file operations, screenshots)
   - Processes commands locally
   - Sends responses back through gRPC stream

3. **Media Announcement**:
   - Scans for local media files
   - Announces files to Edge Service
   - Receives catalog IDs for discovered files

## Configuration

### Network Configuration
- `EDGE_GRPC_ADDRESS`: Address of Edge Service (default: localhost:50051)
- `PEER_ID`: Unique identifier for this peer (auto-generated if not provided)
- `USE_TLS`: Whether to use TLS for gRPC communication (default: false)

### Media Configuration
- `MEDIA_DIRS`: Directories to scan for media files
- `INCLUDE_EXTENSIONS`: File extensions to include (default: .mp4,.mkv,.avi,.mov)
- `SCAN_INTERVAL_MINUTES`: Interval between automatic scans (default: 60)

### WebRTC Configuration
- `STUN_SERVERS`: STUN servers for NAT traversal
- `TURN_SERVERS`: TURN servers for relay
- `WEBRTC_MAX_BANDWIDTH_KBPS`: Maximum streaming bandwidth

## Development

```bash
# Install dependencies
poetry install

# Run service
poetry run python -m src.main start --media-dir /path/to/media
```

## API
### gRPC Interface
- As a gRPC client, the Peer Service implements the PeerEdgeService interface:
- Connects to Edge Service with peer_id in metadata
- Handles incoming EdgeMessage objects

#### File operations (delete, hash, remap)
- Screenshot capture requests
- Catalog operations

#### Sends PeerMessage responses:
- File operation results
- Catalog announcements
- File offers

### WebRTC Streaming
Implements WebRTC operations for media streaming
Negotiates streaming sessions through PeerEdgeService
Supports SDP and ICE candidate exchange