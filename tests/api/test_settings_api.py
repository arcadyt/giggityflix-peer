import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from giggityflix_peer.api.server import ApiServer


class TestSettingsApi:
    """Tests for the settings API endpoints."""

    @pytest.fixture
    def mock_config_service(self):
        """Create a mock config service."""
        mock = MagicMock()
        mock.get_all = AsyncMock()
        mock.get_setting = AsyncMock()
        mock.set = AsyncMock()
        return mock

    @pytest.fixture
    def api_server(self, mock_config_service):
        """Create an API server with mock services."""
        server = ApiServer()
        # Replace the config service with our mock
        server.config_service = mock_config_service
        return server

    @pytest.mark.asyncio
    async def test_handle_get_settings(self, api_server, mock_config_service):
        """Test getting all settings."""
        # Set up the mock to return some settings
        now = datetime.now().isoformat()
        mock_config_service.get_all.return_value = {
            "key1": {
                "value": "value1",
                "value_type": "str",
                "description": "desc1",
                "editable": True,
                "last_updated": now
            },
            "key2": {
                "value": 42,
                "value_type": "int",
                "description": "desc2",
                "editable": True,
                "last_updated": now
            }
        }

        # Create a request
        request = make_mocked_request("GET", "/api/settings")

        # Call the handler
        response = await api_server.handle_get_settings(request)

        # Check that the config service was called correctly
        mock_config_service.get_all.assert_called_once_with(editable_only=True)

        # Check the response
        assert response.status == 200
        data = json.loads(response.text)
        assert len(data["settings"]) == 2
        assert data["settings"][0]["key"] in ["key1", "key2"]
        assert data["settings"][1]["key"] in ["key1", "key2"]
        if data["settings"][0]["key"] == "key1":
            assert data["settings"][0]["value"] == "value1"
            assert data["settings"][1]["value"] == 42
        else:
            assert data["settings"][0]["value"] == 42
            assert data["settings"][1]["value"] == "value1"

    @pytest.mark.asyncio
    async def test_handle_get_setting(self, api_server, mock_config_service):
        """Test getting a specific setting."""
        # Set up the mock to return a setting
        now = datetime.now().isoformat()
        mock_config_service.get_setting.return_value = {
            "key": "test_key",
            "value": "test_value",
            "value_type": "str",
            "description": "test desc",
            "editable": True,
            "last_updated": now
        }

        # Create a request
        request = make_mocked_request("GET", "/api/settings/test_key")
        request.match_info = {"key": "test_key"}

        # Call the handler
        response = await api_server.handle_get_setting(request)

        # Check that the config service was called correctly
        mock_config_service.get_setting.assert_called_once_with("test_key")

        # Check the response
        assert response.status == 200
        data = json.loads(response.text)
        assert data["key"] == "test_key"
        assert data["value"] == "test_value"
        assert data["value_type"] == "str"
        assert data["description"] == "test desc"
        assert data["last_updated"] == now

    @pytest.mark.asyncio
    async def test_handle_get_setting_not_found(self, api_server, mock_config_service):
        """Test getting a nonexistent setting."""
        # Set up the mock to return None
        mock_config_service.get_setting.return_value = None

        # Create a request
        request = make_mocked_request("GET", "/api/settings/nonexistent")
        request.match_info = {"key": "nonexistent"}

        # Call the handler
        response = await api_server.handle_get_setting(request)

        # Check the response
        assert response.status == 404
        data = json.loads(response.text)
        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_get_setting_not_editable(self, api_server, mock_config_service):
        """Test getting a non-editable setting."""
        # Set up the mock to return a non-editable setting
        now = datetime.now().isoformat()
        mock_config_service.get_setting.return_value = {
            "key": "test_key",
            "value": "test_value",
            "value_type": "str",
            "description": "test desc",
            "editable": False,
            "last_updated": now
        }

        # Create a request
        request = make_mocked_request("GET", "/api/settings/test_key")
        request.match_info = {"key": "test_key"}

        # Call the handler
        response = await api_server.handle_get_setting(request)

        # Check the response
        assert response.status == 403
        data = json.loads(response.text)
        assert "error" in data
        assert "not editable" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_update_setting(self, api_server, mock_config_service):
        """Test updating a setting."""
        # Set up the mock to return a setting
        now = datetime.now().isoformat()
        mock_config_service.get_setting.return_value = {
            "key": "test_key",
            "value": "new_value",
            "value_type": "str",
            "description": "test desc",
            "editable": True,
            "last_updated": now
        }

        # Mock the request json method
        async def mock_json():
            return {"value": "new_value"}

        # Create a request
        request = make_mocked_request("PUT", "/api/settings/test_key")
        request.match_info = {"key": "test_key"}
        request.json = mock_json

        # Call the handler
        response = await api_server.handle_update_setting(request)

        # Check that the config service was called correctly
        mock_config_service.set.assert_called_once_with("test_key", "new_value")
        mock_config_service.get_setting.assert_called_once_with("test_key")

        # Check the response
        assert response.status == 200
        data = json.loads(response.text)
        assert data["key"] == "test_key"
        assert data["value"] == "new_value"
        assert data["value_type"] == "str"
        assert data["description"] == "test desc"
        assert data["last_updated"] == now

    @pytest.mark.asyncio
    async def test_handle_update_setting_missing_value(self, api_server):
        """Test updating a setting without providing a value."""
        # Mock the request json method
        async def mock_json():
            return {}

        # Create a request
        request = make_mocked_request("PUT", "/api/settings/test_key")
        request.match_info = {"key": "test_key"}
        request.json = mock_json

        # Call the handler
        response = await api_server.handle_update_setting(request)

        # Check the response
        assert response.status == 400
        data = json.loads(response.text)
        assert "error" in data
        assert "Missing value" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_update_setting_invalid(self, api_server, mock_config_service):
        """Test updating a setting that can't be updated."""
        # Set up the mock to raise a ValueError
        mock_config_service.set.side_effect = ValueError("Setting cannot be updated")

        # Mock the request json method
        async def mock_json():
            return {"value": "new_value"}

        # Create a request
        request = make_mocked_request("PUT", "/api/settings/test_key")
        request.match_info = {"key": "test_key"}
        request.json = mock_json

        # Call the handler
        response = await api_server.handle_update_setting(request)

        # Check the response
        assert response.status == 400
        data = json.loads(response.text)
        assert "error" in data
        assert "Setting cannot be updated" in data["error"]
