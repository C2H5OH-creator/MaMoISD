from fastapi import APIRouter

from src.api.info import router as info_router

api_router = APIRouter()
api_router.include_router(info_router)
