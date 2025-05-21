from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from ..di import container
from ..old_resource_mgmt.resource_pool import ResourcePoolManager
from ..old_services.config_service import config_service

# Create router with prefix
router = APIRouter(
    prefix="/api/resources",
    tags=["resources"],
    responses={404: {"description": "Not found"}},
)


class ProcessPoolUpdate(BaseModel):
    size: int = Field(..., gt=0, description="New process pool size")


class StorageResourceUpdate(BaseModel):
    path: str = Field(..., description="Storage resource path (e.g., 'C:' or '/')")
    io_limit: int = Field(..., gt=0, description="New IO operation limit")


def get_resource_manager():
    """Dependency to get resource manager."""
    return container.resolve(ResourcePoolManager)


@router.get("/pool")
async def get_process_pool_size(
        resource_manager: ResourcePoolManager = Depends(get_resource_manager)
):
    """Get current process pool size."""
    size = await resource_manager.get_process_pool_size()
    return {"size": size}


@router.put("/pool")
async def update_process_pool_size(
        update: ProcessPoolUpdate,
        resource_manager: ResourcePoolManager = Depends(get_resource_manager)
):
    """Update process pool size."""
    success = await resource_manager.resize_process_pool(update.size)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to resize process pool")

    return {"status": "success", "new_size": update.size}


@router.get("/storage")
async def get_storage_resources(
        resource_manager: ResourcePoolManager = Depends(get_resource_manager)
):
    """Get all storage resources and their IO limits."""
    resources = await config_service.get("storage_resources", [])
    return {"resources": resources}


@router.put("/storage")
async def update_storage_resource(
        update: StorageResourceUpdate,
        resource_manager: ResourcePoolManager = Depends(get_resource_manager)
):
    """Update IO limit for a specific storage resource."""
    success = await resource_manager.resize_drive_semaphore(update.path, update.io_limit)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update IO limit")

    return {"status": "success", "path": update.path, "io_limit": update.io_limit}


@router.get("/defaults")
async def get_default_settings():
    """Get default resource settings."""
    default_io_limit = await config_service.get("default_io_limit", 2)
    return {
        "default_io_limit": default_io_limit
    }


@router.put("/defaults/io_limit")
async def update_default_io_limit(limit: int):
    """Update default IO limit."""
    if limit <= 0:
        raise HTTPException(status_code=400, detail="IO limit must be positive")

    await config_service.set("default_io_limit", limit)
    return {"status": "success", "default_io_limit": limit}
