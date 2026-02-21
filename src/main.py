from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api import api_router
from src.db.database import close_engine, create_global_database, create_tables


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_global_database()
    await create_tables()
    try:
        yield
    finally:
        await close_engine()


app = FastAPI(title="МиСПрИС API", lifespan=lifespan)
app.include_router(api_router)
