import tempfile
from pathlib import Path
from unittest import mock

import pytest

from giggityflix_peer.config import config
from giggityflix_peer.old_db.sqlite import Database
from giggityflix_peer.models.media import MediaFile, MediaStatus, MediaType
from giggityflix_peer.old_services.db_service import DatabaseService


@pytest.fixture
async def test_db():
    """Create a temporary database for testing."""
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set up the database path
        with mock.patch.object(config.peer, "data_dir", temp_dir):
            with mock.patch.object(config.db, "path", "test.db"):
                # Create the database
                db = Database()
                await db.initialize()

                yield db

                # Clean up
                await db.close()


@pytest.fixture
async def db_service(test_db):
    """Create a database service for testing."""
    service = DatabaseService()
    await service.initialize()

    yield service

    await service.close()


@pytest.mark.asyncio
async def test_add_and_get_media_file(db_service):
    """Test adding and retrieving a media file."""
    # Create a test media file
    media_file = MediaFile(
        luid="test-luid",
        path=Path("/path/to/test.mp4"),
        size_bytes=1024,
        media_type=MediaType.VIDEO,
        status=MediaStatus.PENDING,
        hashes={"md5": "test-hash"}
    )

    # Add to the database
    await db_service.add_media_file(media_file)

    # Retrieve from the database
    retrieved = await db_service.get_media_file("test-luid")

    # Check that the retrieved file matches the original
    assert retrieved is not None
    assert retrieved.luid == "test-luid"
    assert str(retrieved.path) == "/path/to/test.mp4"
    assert retrieved.size_bytes == 1024
    assert retrieved.media_type == MediaType.VIDEO
    assert retrieved.status == MediaStatus.PENDING
    assert "md5" in retrieved.hashes
    assert retrieved.hashes["md5"] == "test-hash"


@pytest.mark.asyncio
async def test_update_media_file(db_service):
    """Test updating a media file."""
    # Create a test media file
    media_file = MediaFile(
        luid="test-luid",
        path=Path("/path/to/test.mp4"),
        size_bytes=1024,
        media_type=MediaType.VIDEO,
        status=MediaStatus.PENDING,
        hashes={"md5": "test-hash"}
    )

    # Add to the database
    await db_service.add_media_file(media_file)

    # Update the media file
    media_file.size_bytes = 2048
    media_file.status = MediaStatus.READY
    media_file.hashes = {"md5": "new-hash"}

    await db_service.update_media_file(media_file)

    # Retrieve from the database
    retrieved = await db_service.get_media_file("test-luid")

    # Check that the retrieved file has been updated
    assert retrieved is not None
    assert retrieved.size_bytes == 2048
    assert retrieved.status == MediaStatus.READY
    assert retrieved.hashes["md5"] == "new-hash"


@pytest.mark.asyncio
async def test_get_all_media_files(db_service):
    """Test retrieving all media files."""
    # Create test media files
    media_file1 = MediaFile(
        luid="test-luid-1",
        path=Path("/path/to/test1.mp4"),
        size_bytes=1024,
        media_type=MediaType.VIDEO,
        status=MediaStatus.PENDING
    )

    media_file2 = MediaFile(
        luid="test-luid-2",
        path=Path("/path/to/test2.mp3"),
        size_bytes=512,
        media_type=MediaType.AUDIO,
        status=MediaStatus.READY
    )

    # Add to the database
    await db_service.add_media_file(media_file1)
    await db_service.add_media_file(media_file2)

    # Retrieve all files
    all_files = await db_service.get_all_media_files()

    # Check that both files were retrieved
    assert len(all_files) == 2

    # Check that the files have the correct LUIDs
    luids = {file.luid for file in all_files}
    assert "test-luid-1" in luids
    assert "test-luid-2" in luids

    # Check that the files have the correct media types
    for file in all_files:
        if file.luid == "test-luid-1":
            assert file.media_type == MediaType.VIDEO
        elif file.luid == "test-luid-2":
            assert file.media_type == MediaType.AUDIO


@pytest.mark.asyncio
async def test_get_media_file_by_path(db_service):
    """Test retrieving a media file by its path."""
    # Create a test media file
    media_file = MediaFile(
        luid="test-luid",
        path=Path("/path/to/test.mp4"),
        size_bytes=1024,
        media_type=MediaType.VIDEO,
        status=MediaStatus.PENDING
    )

    # Add to the database
    await db_service.add_media_file(media_file)

    # Retrieve by path
    retrieved = await db_service.get_media_file_by_path("/path/to/test.mp4")

    # Check that the retrieved file matches the original
    assert retrieved is not None
    assert retrieved.luid == "test-luid"


@pytest.mark.asyncio
async def test_update_media_catalog_id(db_service):
    """Test updating the catalog ID of a media file."""
    # Create a test media file
    media_file = MediaFile(
        luid="test-luid",
        path=Path("/path/to/test.mp4"),
        size_bytes=1024,
        media_type=MediaType.VIDEO,
        status=MediaStatus.PENDING
    )

    # Add to the database
    await db_service.add_media_file(media_file)

    # Update the catalog ID
    await db_service.update_media_catalog_id("test-luid", "test-catalog-id")

    # Retrieve the updated file
    retrieved = await db_service.get_media_file("test-luid")

    # Check that the catalog ID has been updated
    assert retrieved is not None
    assert retrieved.catalog_id == "test-catalog-id"
