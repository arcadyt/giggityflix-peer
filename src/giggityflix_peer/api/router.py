from fastapi import APIRouter

from .resource_api import router as resource_router

# API router that includes resource management endpoints
api_router = APIRouter()

# Include resource management endpoints
api_router.include_router(resource_router)
