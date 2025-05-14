import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set environment variables for testing
os.environ["EDGE_GRPC_ADDRESS"] = "localhost:50051"
os.environ["GRPC_RECONNECT_INTERVAL_SEC"] = "1"
os.environ["GRPC_MAX_RECONNECT_ATTEMPTS"] = "2"
os.environ["GRPC_TIMEOUT_SEC"] = "1"
os.environ["DB_PATH"] = "test.db"
os.environ["MEDIA_DIRS"] = "/tmp/test-media"
os.environ["LOG_LEVEL"] = "DEBUG"
os.environ["PEER_ID"] = "test-peer-id"
os.environ["DATA_DIR"] = "/tmp/test-data"
