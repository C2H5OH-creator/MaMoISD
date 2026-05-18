from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api import api_router
from src.db.database import close_engine, create_global_database, create_tables

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def web_app() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
