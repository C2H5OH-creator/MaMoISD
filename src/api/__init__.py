from fastapi import APIRouter

from src.api.database import router as database_router
from src.api.info import router as info_router

api_router = APIRouter()
api_router.include_router(info_router)
api_router.include_router(database_router)
