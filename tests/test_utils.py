import sys
from unittest import mock

from giggityflix_peer.utils.logging import setup_logging


class TestLogging:
    """Test the logging configuration."""

    def test_setup_logging(self):
        """Test setting up logging."""
        # Mock the logging module
        with mock.patch("logging.getLogger") as mock_get_logger, \
             mock.patch("logging.StreamHandler") as mock_stream_handler, \
             mock.patch("logging.handlers.RotatingFileHandler") as mock_file_handler, \
             mock.patch("colorlog.ColoredFormatter") as mock_color_formatter, \
             mock.patch("logging.Formatter") as mock_formatter, \
             mock.patch("src.utils.logging.os.makedirs") as mock_makedirs, \
             mock.patch("src.utils.logging.config") as mock_config:
            
            # Configure mocks
            mock_root_logger = mock.MagicMock()
            mock_get_logger.return_value = mock_root_logger
            
            mock_stream_handler_instance = mock.MagicMock()
            mock_stream_handler.return_value = mock_stream_handler_instance
            
            mock_file_handler_instance = mock.MagicMock()
            mock_file_handler.return_value = mock_file_handler_instance
            
            mock_color_formatter_instance = mock.MagicMock()
            mock_color_formatter.return_value = mock_color_formatter_instance
            
            mock_formatter_instance = mock.MagicMock()
            mock_formatter.return_value = mock_formatter_instance
            
            # Configure config
            mock_config.logging.level = "INFO"
            mock_config.logging.log_dir = "/tmp/logs"
            mock_config.logging.max_size_mb = 10
            mock_config.logging.backup_count = 5
            mock_config.logging.use_color = True
            
            # Call the function
            setup_logging()
            
            # Verify
            mock_makedirs.assert_called_once_with("/tmp/logs", exist_ok=True)
            mock_get_logger.assert_called_once_with()
            mock_root_logger.setLevel.assert_called_once_with("INFO")
            
            # Check formatters
            mock_color_formatter.assert_called_once()
            mock_formatter.assert_called_once()
            
            # Check handlers
            mock_stream_handler.assert_called_once_with(sys.stdout)
            mock_stream_handler_instance.setFormatter.assert_called_once_with(mock_color_formatter_instance)
            
            mock_file_handler.assert_called_once()
            mock_file_handler_instance.setFormatter.assert_called_once_with(mock_formatter_instance)
            
            # Check that handlers were added
            assert mock_root_logger.addHandler.call_count == 2
            mock_root_logger.addHandler.assert_any_call(mock_stream_handler_instance)
            mock_root_logger.addHandler.assert_any_call(mock_file_handler_instance)

    def test_setup_logging_no_color(self):
        """Test setting up logging without color."""
        # Mock the logging module
        with mock.patch("logging.getLogger") as mock_get_logger, \
             mock.patch("logging.StreamHandler") as mock_stream_handler, \
             mock.patch("logging.handlers.RotatingFileHandler") as mock_file_handler, \
             mock.patch("logging.Formatter") as mock_formatter, \
             mock.patch("src.utils.logging.os.makedirs") as mock_makedirs, \
             mock.patch("src.utils.logging.config") as mock_config:
            
            # Configure mocks
            mock_root_logger = mock.MagicMock()
            mock_get_logger.return_value = mock_root_logger
            
            mock_stream_handler_instance = mock.MagicMock()
            mock_stream_handler.return_value = mock_stream_handler_instance
            
            mock_file_handler_instance = mock.MagicMock()
            mock_file_handler.return_value = mock_file_handler_instance
            
            mock_formatter_instance = mock.MagicMock()
            mock_formatter.return_value = mock_formatter_instance
            
            # Configure config
            mock_config.logging.level = "INFO"
            mock_config.logging.log_dir = "/tmp/logs"
            mock_config.logging.max_size_mb = 10
            mock_config.logging.backup_count = 5
            mock_config.logging.use_color = False
            
            # Call the function
            setup_logging()
            
            # Verify - no color formatter should be created
            mock_formatter.assert_called()
            mock_stream_handler_instance.setFormatter.assert_called_once_with(mock_formatter_instance)
