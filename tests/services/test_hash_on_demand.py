from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from giggityflix_grpc_peer import peer_edge_pb2 as pb2
from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType
from giggityflix_peer.services.edge_client import EdgeClient


class TestHashOnDemand:
    """Tests for on-demand hash calculation in the EdgeClient."""

    @pytest.fixture
    def edge_client(self):
        """Create an EdgeClient with mocked stream."""
        client = EdgeClient("test_peer_id")
        client._stream = AsyncMock()
        client._connected = True
        return client

    @pytest.mark.asyncio
    async def test_handle_file_hash_request(self, edge_client):
        """Test handling a file hash request from the Edge Service."""
        # Create a mock request
        request = pb2.FileHashRequest(
            catalog_uuid="test_catalog_id",
            hash_types=["md5", "sha1", "sha256"]
        )
        
        # Mock the database service
        mock_db_service = MagicMock()
        mock_media_file = MediaFile(
            luid="test_luid",
            path="/test/media/test.mp4",
            catalog_id="test_catalog_id",
            size_bytes=1000,
            media_type=MediaType.VIDEO,
            status=MediaStatus.READY,
            hashes={"md5": "existing_md5_hash"}  # Only MD5 is pre-calculated
        )
        mock_db_service.get_media_file_by_catalog_id = AsyncMock(return_value=mock_media_file)
        mock_db_service.update_media_file = AsyncMock()
        
        # Mock the calculate_file_hash function
        mock_calculate_hash = AsyncMock(side_effect=lambda path, algorithm: f"{algorithm}_hash_value")
        
        # Patch the necessary imports
        with patch("giggityflix_peer.services.edge_client.db_service", mock_db_service), \
             patch("giggityflix_peer.services.edge_client.calculate_file_hash", mock_calculate_hash):
            
            # Call the method
            await edge_client.handle_file_hash_request(request, "test_request_id")
            
            # Check that the database was queried for the media file
            mock_db_service.get_media_file_by_catalog_id.assert_called_once_with("test_catalog_id")
            
            # Check that calculate_file_hash was called for sha1 and sha256, but not md5 (already exists)
            assert mock_calculate_hash.call_count == 2
            mock_calculate_hash.assert_any_call(mock_media_file.path, "sha1")
            mock_calculate_hash.assert_any_call(mock_media_file.path, "sha256")
            
            # Check that the database was updated with the new hashes
            mock_db_service.update_media_file.assert_called_once()
            updated_file = mock_db_service.update_media_file.call_args[0][0]
            assert updated_file.hashes["md5"] == "existing_md5_hash"
            assert updated_file.hashes["sha1"] == "sha1_hash_value"
            assert updated_file.hashes["sha256"] == "sha256_hash_value"
            
            # Check that the response was sent with all three hashes
            edge_client._stream.write.assert_called_once()
            response = edge_client._stream.write.call_args[0][0]
            assert response.request_id == "test_request_id"
            assert response.HasField('file_hash_response')
            assert response.file_hash_response.catalog_uuid == "test_catalog_id"
            assert response.file_hash_response.hashes["md5"] == "existing_md5_hash"
            assert response.file_hash_response.hashes["sha1"] == "sha1_hash_value"
            assert response.file_hash_response.hashes["sha256"] == "sha256_hash_value"

    @pytest.mark.asyncio
    async def test_handle_file_hash_request_media_not_found(self, edge_client):
        """Test handling a file hash request when the media file is not found."""
        # Create a mock request
        request = pb2.FileHashRequest(
            catalog_uuid="nonexistent_id",
            hash_types=["md5", "sha1"]
        )
        
        # Mock the database service to return None
        mock_db_service = MagicMock()
        mock_db_service.get_media_file_by_catalog_id = AsyncMock(return_value=None)
        
        # Patch the necessary imports
        with patch("giggityflix_peer.services.edge_client.db_service", mock_db_service):
            
            # Call the method
            await edge_client.handle_file_hash_request(request, "test_request_id")
            
            # Check that the database was queried for the media file
            mock_db_service.get_media_file_by_catalog_id.assert_called_once_with("nonexistent_id")
            
            # Check that the error response was sent
            edge_client._stream.write.assert_called_once()
            response = edge_client._stream.write.call_args[0][0]
            assert response.request_id == "test_request_id"
            assert response.HasField('file_hash_response')
            assert response.file_hash_response.catalog_uuid == "nonexistent_id"
            assert response.file_hash_response.error_message == "Media file not found"

    @pytest.mark.asyncio
    async def test_handle_file_hash_request_calculation_error(self, edge_client):
        """Test handling a file hash request when hash calculation fails."""
        # Create a mock request
        request = pb2.FileHashRequest(
            catalog_uuid="test_catalog_id",
            hash_types=["md5", "sha1"]
        )
        
        # Mock the database service
        mock_db_service = MagicMock()
        mock_media_file = MediaFile(
            luid="test_luid",
            path="/test/media/test.mp4",
            catalog_id="test_catalog_id",
            size_bytes=1000,
            media_type=MediaType.VIDEO,
            status=MediaStatus.READY,
            hashes={}  # No pre-calculated hashes
        )
        mock_db_service.get_media_file_by_catalog_id = AsyncMock(return_value=mock_media_file)
        mock_db_service.update_media_file = AsyncMock()
        
        # Mock the calculate_file_hash function to raise an exception for sha1
        def mock_hash_side_effect(path, algorithm):
            if algorithm == "sha1":
                raise Exception("Hash calculation failed")
            return f"{algorithm}_hash_value"
        
        mock_calculate_hash = AsyncMock(side_effect=mock_hash_side_effect)
        
        # Patch the necessary imports
        with patch("giggityflix_peer.services.edge_client.db_service", mock_db_service), \
             patch("giggityflix_peer.services.edge_client.calculate_file_hash", mock_calculate_hash):
            
            # Call the method
            await edge_client.handle_file_hash_request(request, "test_request_id")
            
            # Check that calculate_file_hash was called for both algorithms
            assert mock_calculate_hash.call_count == 2
            
            # Check that the response was sent with only the successful hash
            edge_client._stream.write.assert_called_once()
            response = edge_client._stream.write.call_args[0][0]
            assert response.request_id == "test_request_id"
            assert response.HasField('file_hash_response')
            assert response.file_hash_response.catalog_uuid == "test_catalog_id"
            assert response.file_hash_response.hashes["md5"] == "md5_hash_value"
            assert "sha1" not in response.file_hash_response.hashes
