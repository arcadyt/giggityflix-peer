from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from giggityflix_peer.services.config_service import ConfigService


class TestConfigService:
    """Tests for the ConfigService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_db.execute_and_fetchone = AsyncMock()
        mock_db.execute_and_fetchall = AsyncMock()
        mock_db.transaction = MagicMock()
        # Create a context manager for the transaction
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_db.transaction.return_value = mock_context
        return mock_db

    @pytest.fixture
    def config_service(self, mock_db):
        """Create a config service with a mock database."""
        service = ConfigService()
        # Replace the db with our mock
        service._db = mock_db
        return service

    @pytest.mark.asyncio
    async def test_initialize(self, config_service, mock_db):
        """Test the initialize method."""
        # Set up the mock to return no settings
        mock_db.execute_and_fetchone.return_value = None
        mock_db.execute_and_fetchall.return_value = []

        # Call the method
        await config_service.initialize()

        # Check that the database was called correctly for each default setting
        assert mock_db.execute_and_fetchone.call_count == len(config_service._defaults)
        assert mock_db.execute.call_count == len(config_service._defaults)

    @pytest.mark.asyncio
    async def test_get_existing_setting(self, config_service):
        """Test getting an existing setting from the cache."""
        # Set up the cache with a test setting
        config_service._cache = {"test_key": "test_value"}

        # Get the setting
        value = await config_service.get("test_key", "default")

        # Check that the correct value was returned
        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_get_nonexistent_setting(self, config_service):
        """Test getting a nonexistent setting."""
        # Set up an empty cache
        config_service._cache = {}

        # Get a nonexistent setting
        value = await config_service.get("nonexistent", "default")

        # Check that the default was returned
        assert value == "default"

    @pytest.mark.asyncio
    async def test_set_valid_setting(self, config_service, mock_db):
        """Test setting a valid setting."""
        # Set up the mock to return a setting
        mock_db.execute_and_fetchone.return_value = {
            "key": "test_key",
            "value": "old_value",
            "value_type": "str",
            "editable": True
        }

        # Call the method
        await config_service.set("test_key", "new_value")

        # Check that the database was called correctly
        mock_db.execute.assert_called_once()
        # Check that the cache was updated
        assert config_service._cache["test_key"] == "new_value"

    @pytest.mark.asyncio
    async def test_set_nonexistent_setting(self, config_service, mock_db):
        """Test setting a nonexistent setting."""
        # Set up the mock to return no setting
        mock_db.execute_and_fetchone.return_value = None

        # Call the method and check that it raises a ValueError
        with pytest.raises(ValueError, match="does not exist"):
            await config_service.set("nonexistent", "value")

    @pytest.mark.asyncio
    async def test_set_non_editable_setting(self, config_service, mock_db):
        """Test setting a non-editable setting."""
        # Set up the mock to return a non-editable setting
        mock_db.execute_and_fetchone.return_value = {
            "key": "test_key",
            "value": "old_value",
            "value_type": "str",
            "editable": False
        }

        # Call the method and check that it raises a ValueError
        with pytest.raises(ValueError, match="not editable"):
            await config_service.set("test_key", "new_value")

    @pytest.mark.asyncio
    async def test_get_all_settings(self, config_service, mock_db):
        """Test getting all settings."""
        # Set up the mock to return some settings
        mock_db.execute_and_fetchall.return_value = [
            {
                "key": "key1",
                "value": "value1",
                "value_type": "str",
                "description": "desc1",
                "editable": True,
                "last_updated": datetime.now().isoformat()
            },
            {
                "key": "key2",
                "value": "42",
                "value_type": "int",
                "description": "desc2",
                "editable": True,
                "last_updated": datetime.now().isoformat()
            }
        ]

        # Call the method
        settings = await config_service.get_all()

        # Check that the correct settings were returned
        assert len(settings) == 2
        assert settings["key1"]["value"] == "value1"
        assert settings["key2"]["value"] == 42  # Converted to int

    @pytest.mark.asyncio
    async def test_get_setting(self, config_service, mock_db):
        """Test getting a specific setting."""
        # Set up the mock to return a setting
        setting_time = datetime.now().isoformat()
        mock_db.execute_and_fetchone.return_value = {
            "key": "test_key",
            "value": "42",
            "value_type": "int",
            "description": "test desc",
            "editable": True,
            "last_updated": setting_time
        }

        # Call the method
        setting = await config_service.get_setting("test_key")

        # Check that the correct setting was returned
        assert setting["key"] == "test_key"
        assert setting["value"] == 42  # Converted to int
        assert setting["description"] == "test desc"
        assert setting["editable"] is True
        assert setting["last_updated"] == setting_time

    def test_convert_value(self, config_service):
        """Test converting values from strings to their proper types."""
        # Test string conversion
        assert config_service._convert_value("test", "str") == "test"

        # Test int conversion
        assert config_service._convert_value("42", "int") == 42

        # Test bool conversion
        assert config_service._convert_value("true", "bool") is True
        assert config_service._convert_value("false", "bool") is False

        # Test json conversion
        assert config_service._convert_value('["a", "b"]', "json") == ["a", "b"]
        assert config_service._convert_value('{"key": "value"}', "json") == {"key": "value"}

    def test_convert_to_string(self, config_service):
        """Test converting values to strings based on their types."""
        # Test string conversion
        assert config_service._convert_to_string("test", "str") == "test"

        # Test int conversion
        assert config_service._convert_to_string(42, "int") == "42"

        # Test bool conversion
        assert config_service._convert_to_string(True, "bool") == "true"
        assert config_service._convert_to_string(False, "bool") == "false"

        # Test json conversion
        assert config_service._convert_to_string(["a", "b"], "json") == '["a", "b"]'
        assert config_service._convert_to_string({"key": "value"}, "json") == '{"key": "value"}'
