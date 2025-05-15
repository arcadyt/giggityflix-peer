import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import aiosqlite

from giggityflix_peer.config import config

logger = logging.getLogger(__name__)


class Database:
    """Asynchronous SQLite database wrapper."""

    def __init__(self):
        """Initialize the database."""
        self._db_path = Path(config.peer.data_dir) / config.db.path
        self._backup_dir = Path(config.peer.data_dir) / config.db.backup_dir
        self._conn: Optional[aiosqlite.Connection] = None
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the database connection and schema."""
        # Ensure data directory exists
        os.makedirs(Path(config.peer.data_dir), exist_ok=True)
        os.makedirs(self._backup_dir, exist_ok=True)

        async with self._lock:
            if self._initialized:
                return

            logger.info(f"Initializing database at {self._db_path}")

            # Connect to the database
            self._conn = await aiosqlite.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row

            # Enable foreign keys
            await self._conn.execute("PRAGMA foreign_keys = ON")

            # Enable WAL mode for better concurrency
            await self._conn.execute("PRAGMA journal_mode = WAL")

            # Create tables
            await self._create_tables()

            self._initialized = True
            logger.info("Database initialization complete")

    async def close(self) -> None:
        """Close the database connection."""
        async with self._lock:
            if self._conn:
                await self._conn.close()
                self._conn = None
                self._initialized = False
                logger.info("Database connection closed")

    async def backup(self) -> str:
        """Backup the database."""
        async with self._lock:
            if not self._conn:
                raise RuntimeError("Database not initialized")

            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            backup_path = self._backup_dir / f"peer_{timestamp}.db"

            # Create a new connection for the backup
            # This is done because Python's sqlite3 doesn't support async for backup
            # We'll need to use the synchronous API
            source_conn = sqlite3.connect(self._db_path)
            dest_conn = sqlite3.connect(backup_path)

            try:
                # Run the backup on the thread pool
                await asyncio.to_thread(
                    lambda: source_conn.backup(dest_conn)
                )
                logger.info(f"Database backed up to {backup_path}")
                return str(backup_path)
            finally:
                # Close the connections
                source_conn.close()
                dest_conn.close()

    async def _create_tables(self) -> None:
        """Create the database tables if they don't exist."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        # Media files table
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS media_files (
            luid TEXT PRIMARY KEY,
            catalog_id TEXT,
            path TEXT NOT NULL,
            relative_path TEXT,
            size_bytes INTEGER NOT NULL,
            media_type TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            modified_at TEXT,
            last_accessed TEXT,
            duration_seconds REAL,
            width INTEGER,
            height INTEGER,
            codec TEXT,
            bitrate INTEGER,
            framerate REAL,
            view_count INTEGER DEFAULT 0,
            last_viewed TEXT,
            error_message TEXT
        )
        """)

        # Media hashes table
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS media_hashes (
            luid TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            hash_value TEXT NOT NULL,
            PRIMARY KEY (luid, algorithm),
            FOREIGN KEY (luid) REFERENCES media_files (luid) ON DELETE CASCADE
        )
        """)

        # Screenshots table
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id TEXT PRIMARY KEY,
            media_luid TEXT NOT NULL,
            timestamp REAL NOT NULL,
            path TEXT NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (media_luid) REFERENCES media_files (luid) ON DELETE CASCADE
        )
        """)

        # Media collections table
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS media_collections (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            media_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            modified_at TEXT
        )
        """)

        # Collection items table
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS collection_items (
            collection_id TEXT NOT NULL,
            media_luid TEXT NOT NULL,
            PRIMARY KEY (collection_id, media_luid),
            FOREIGN KEY (collection_id) REFERENCES media_collections (id) ON DELETE CASCADE,
            FOREIGN KEY (media_luid) REFERENCES media_files (luid) ON DELETE CASCADE
        )
        """)

        # Collection metadata table
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS collection_metadata (
            collection_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (collection_id, key),
            FOREIGN KEY (collection_id) REFERENCES media_collections (id) ON DELETE CASCADE
        )
        """)

        # Create indexes
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_media_files_catalog_id ON media_files (catalog_id)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_media_files_media_type ON media_files (media_type)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_media_files_status ON media_files (status)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_screenshots_media_luid ON screenshots (media_luid)")

        await self._conn.commit()

    async def execute(self, query: str, params: Union[Tuple, Dict[str, Any], None] = None) -> aiosqlite.Cursor:
        """Execute a SQL query."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        async with self._lock:
            return await self._conn.execute(query, params or ())

    async def executemany(self, query: str, params_seq: List[Union[Tuple, Dict[str, Any]]]) -> aiosqlite.Cursor:
        """Execute a SQL query with multiple parameter sets."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        async with self._lock:
            return await self._conn.executemany(query, params_seq)

    async def execute_and_fetchall(self, query: str, params: Union[Tuple, Dict[str, Any], None] = None) -> List[
        sqlite3.Row]:
        """Execute a SQL query and fetch all results."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        async with self._lock:
            cursor = await self._conn.execute(query, params or ())
            return await cursor.fetchall()

    async def execute_and_fetchone(self, query: str, params: Union[Tuple, Dict[str, Any], None] = None) -> Optional[
        sqlite3.Row]:
        """Execute a SQL query and fetch one result."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        async with self._lock:
            cursor = await self._conn.execute(query, params or ())
            return await cursor.fetchone()

    async def commit(self) -> None:
        """Commit the current transaction."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        async with self._lock:
            await self._conn.commit()

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        async with self._lock:
            await self._conn.rollback()

    async def transaction(self):
        """Context manager for a transaction."""
        if not self._conn:
            raise RuntimeError("Database not initialized")

        class Transaction:
            def __init__(self, db):
                self.db = db

            async def __aenter__(self):
                await self.db._lock.acquire()
                return self.db

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                try:
                    if exc_type is not None:
                        await self.db._conn.rollback()
                    else:
                        await self.db._conn.commit()
                finally:
                    self.db._lock.release()

        return Transaction(self)


# Create a singleton database instance
db = Database()
