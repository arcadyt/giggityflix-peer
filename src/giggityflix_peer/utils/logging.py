import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorlog

from giggityflix_peer.config import config


def setup_logging() -> None:
    """Configure logging for the application."""
    # Create logs directory if it doesn't exist
    log_dir = Path(config.logging.log_dir)
    os.makedirs(log_dir, exist_ok=True)
    
    # Create a root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(config.logging.level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    if config.logging.use_color:
        # Color formatter for console output
        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    else:
        # Plain formatter for console output
        console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    # File formatter
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # Create file handler
    log_file = log_dir / "peer.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=config.logging.max_size_mb * 1024 * 1024,
        backupCount=config.logging.backup_count
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Set logging levels for third-party libraries
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("grpc").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)
