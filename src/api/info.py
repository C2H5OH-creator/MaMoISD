from fastapi import APIRouter

router = APIRouter(prefix="/info", tags=["info"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}
