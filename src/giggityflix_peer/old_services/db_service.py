import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from giggityflix_peer.old_db.sqlite import db
from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType, Screenshot

logger = logging.getLogger(__name__)


class DatabaseService:
    """Service for database operations related to media files."""

    async def initialize(self) -> None:
        """Initialize the database."""
        await db.initialize()

    async def close(self) -> None:
        """Close the database connection."""
        await db.close()

    async def backup(self) -> str:
        """Backup the database."""
        return await db.backup()

    async def add_media_file(self, media_file: MediaFile) -> None:
        """Add a media file to the database."""
        # Convert Path to string
        path_str = str(media_file.path)

        # Convert datetime objects to ISO format strings
        created_at = media_file.created_at.isoformat()
        modified_at = media_file.modified_at.isoformat() if media_file.modified_at else None
        last_accessed = media_file.last_accessed.isoformat() if media_file.last_accessed else None
        last_viewed = media_file.last_viewed.isoformat() if media_file.last_viewed else None

        async with db.transaction():
            # Insert into media_files table
            await db.execute(
                """
                INSERT INTO media_files (
                    luid, catalog_id, path, relative_path, size_bytes, media_type, status,
                    created_at, modified_at, last_accessed, duration_seconds, width, height,
                    codec, bitrate, framerate, view_count, last_viewed, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    media_file.luid, media_file.catalog_id, path_str, media_file.relative_path,
                    media_file.size_bytes, media_file.media_type.value, media_file.status.value,
                    created_at, modified_at, last_accessed, media_file.duration_seconds,
                    media_file.width, media_file.height, media_file.codec, media_file.bitrate,
                    media_file.framerate, media_file.view_count, last_viewed, media_file.error_message
                )
            )

            # Insert hashes
            if media_file.hashes:
                hash_params = [(media_file.luid, algorithm, hash_value)
                               for algorithm, hash_value in media_file.hashes.items()]

                await db.executemany(
                    """
                    INSERT INTO media_hashes (luid, algorithm, hash_value)
                    VALUES (?, ?, ?)
                    """,
                    hash_params
                )

    async def update_media_file(self, media_file: MediaFile) -> None:
        """Update a media file in the database."""
        # Convert Path to string
        path_str = str(media_file.path)

        # Convert datetime objects to ISO format strings
        modified_at = media_file.modified_at.isoformat() if media_file.modified_at else None
        last_accessed = media_file.last_accessed.isoformat() if media_file.last_accessed else None
        last_viewed = media_file.last_viewed.isoformat() if media_file.last_viewed else None

        async with db.transaction():
            # Update media_files table
            await db.execute(
                """
                UPDATE media_files SET
                    catalog_id = ?, path = ?, relative_path = ?, size_bytes = ?,
                    media_type = ?, status = ?, modified_at = ?, last_accessed = ?,
                    duration_seconds = ?, width = ?, height = ?, codec = ?,
                    bitrate = ?, framerate = ?, view_count = ?, last_viewed = ?,
                    error_message = ?
                WHERE luid = ?
                """,
                (
                    media_file.catalog_id, path_str, media_file.relative_path, media_file.size_bytes,
                    media_file.media_type.value, media_file.status.value, modified_at, last_accessed,
                    media_file.duration_seconds, media_file.width, media_file.height, media_file.codec,
                    media_file.bitrate, media_file.framerate, media_file.view_count, last_viewed,
                    media_file.error_message, media_file.luid
                )
            )

            # Update hashes - first delete existing ones
            await db.execute("DELETE FROM media_hashes WHERE luid = ?", (media_file.luid,))

            # Then insert new ones
            if media_file.hashes:
                hash_params = [(media_file.luid, algorithm, hash_value)
                               for algorithm, hash_value in media_file.hashes.items()]

                await db.executemany(
                    """
                    INSERT INTO media_hashes (luid, algorithm, hash_value)
                    VALUES (?, ?, ?)
                    """,
                    hash_params
                )

    async def get_media_file(self, luid: str) -> Optional[MediaFile]:
        """Get a media file by its local unique ID."""
        # Fetch the media file
        row = await db.execute_and_fetchone(
            "SELECT * FROM media_files WHERE luid = ?", (luid,)
        )

        if not row:
            return None

        # Fetch hashes
        hash_rows = await db.execute_and_fetchall(
            "SELECT algorithm, hash_value FROM media_hashes WHERE luid = ?", (luid,)
        )

        hashes = {row['algorithm']: row['hash_value'] for row in hash_rows}

        # Convert to MediaFile object
        return self._row_to_media_file(row, hashes)

    async def get_media_file_by_path(self, path: str) -> Optional[MediaFile]:
        """Get a media file by its path."""
        # Fetch the media file
        row = await db.execute_and_fetchone(
            "SELECT * FROM media_files WHERE path = ?", (path,)
        )

        if not row:
            return None

        # Fetch hashes
        hash_rows = await db.execute_and_fetchall(
            "SELECT algorithm, hash_value FROM media_hashes WHERE luid = ?", (row['luid'],)
        )

        hashes = {row['algorithm']: row['hash_value'] for row in hash_rows}

        # Convert to MediaFile object
        return self._row_to_media_file(row, hashes)

    async def get_media_file_by_catalog_id(self, catalog_id: str) -> Optional[MediaFile]:
        """Get a media file by its catalog ID."""
        # Fetch the media file
        row = await db.execute_and_fetchone(
            "SELECT * FROM media_files WHERE catalog_id = ?", (catalog_id,)
        )

        if not row:
            return None

        # Fetch hashes
        hash_rows = await db.execute_and_fetchall(
            "SELECT algorithm, hash_value FROM media_hashes WHERE luid = ?", (row['luid'],)
        )

        hashes = {row['algorithm']: row['hash_value'] for row in hash_rows}

        # Convert to MediaFile object
        return self._row_to_media_file(row, hashes)

    async def get_all_media_files(self) -> List[MediaFile]:
        """Get all media files."""
        # Fetch all media files
        rows = await db.execute_and_fetchall("SELECT * FROM media_files")

        result = []
        for row in rows:
            # Fetch hashes for this file
            hash_rows = await db.execute_and_fetchall(
                "SELECT algorithm, hash_value FROM media_hashes WHERE luid = ?", (row['luid'],)
            )

            hashes = {row['algorithm']: row['hash_value'] for row in hash_rows}

            # Convert to MediaFile object
            media_file = self._row_to_media_file(row, hashes)
            result.append(media_file)

        return result

    async def add_screenshot(self, screenshot: Screenshot) -> None:
        """Add a screenshot to the database."""
        # Convert Path to string
        path_str = str(screenshot.path)

        # Convert datetime objects to ISO format strings
        created_at = screenshot.created_at.isoformat()

        # Insert into screenshots table
        await db.execute(
            """
            INSERT INTO screenshots (
                id, media_luid, timestamp, path, width, height, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                screenshot.id, screenshot.media_luid, screenshot.timestamp,
                path_str, screenshot.width, screenshot.height, created_at
            )
        )

    async def get_screenshots_for_media(self, media_luid: str) -> List[Screenshot]:
        """Get all screenshots for a media file."""
        # Fetch screenshots
        rows = await db.execute_and_fetchall(
            "SELECT * FROM screenshots WHERE media_luid = ?", (media_luid,)
        )

        return [self._row_to_screenshot(row) for row in rows]

    async def update_media_catalog_id(self, luid: str, catalog_id: str) -> None:
        """Update the catalog ID for a media file."""
        await db.execute(
            "UPDATE media_files SET catalog_id = ? WHERE luid = ?",
            (catalog_id, luid)
        )

    async def update_media_status(self, luid: str, status: MediaStatus) -> None:
        """Update the status of a media file."""
        await db.execute(
            "UPDATE media_files SET status = ? WHERE luid = ?",
            (status.value, luid)
        )

    async def increment_view_count(self, luid: str) -> None:
        """Increment the view count for a media file."""
        now = datetime.now().isoformat()

        await db.execute(
            """
            UPDATE media_files 
            SET view_count = view_count + 1, last_viewed = ? 
            WHERE luid = ?
            """,
            (now, luid)
        )

    def _row_to_media_file(self, row: sqlite3.Row, hashes: Dict[str, str]) -> MediaFile:
        """Convert a database row to a MediaFile object."""
        # Parse datetime strings
        created_at = datetime.fromisoformat(row['created_at']) if row['created_at'] else None
        modified_at = datetime.fromisoformat(row['modified_at']) if row['modified_at'] else None
        last_accessed = datetime.fromisoformat(row['last_accessed']) if row['last_accessed'] else None
        last_viewed = datetime.fromisoformat(row['last_viewed']) if row['last_viewed'] else None

        return MediaFile(
            luid=row['luid'],
            catalog_id=row['catalog_id'],
            path=Path(row['path']),
            relative_path=row['relative_path'],
            size_bytes=row['size_bytes'],
            media_type=MediaType(row['media_type']),
            status=MediaStatus(row['status']),
            created_at=created_at or datetime.now(),
            modified_at=modified_at,
            last_accessed=last_accessed,
            duration_seconds=row['duration_seconds'],
            width=row['width'],
            height=row['height'],
            codec=row['codec'],
            bitrate=row['bitrate'],
            framerate=row['framerate'],
            view_count=row['view_count'],
            last_viewed=last_viewed,
            error_message=row['error_message'],
            hashes=hashes
        )

    def _row_to_screenshot(self, row: sqlite3.Row) -> Screenshot:
        """Convert a database row to a Screenshot object."""
        # Parse datetime strings
        created_at = datetime.fromisoformat(row['created_at']) if row['created_at'] else None

        return Screenshot(
            id=row['id'],
            media_luid=row['media_luid'],
            timestamp=row['timestamp'],
            path=Path(row['path']),
            width=row['width'],
            height=row['height'],
            created_at=created_at or datetime.now()
        )


# Create a singleton service instance
db_service = DatabaseService()
