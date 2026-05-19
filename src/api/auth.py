import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, examples=["admin"])
    password: str = Field(min_length=1, examples=["admin"])


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    expires_in: int


class CurrentUserResponse(BaseModel):
    username: str
    role: str


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str


def _token_secret() -> str:
    return os.getenv("AUTH_SECRET", "mispris-dev-secret")


def _token_ttl_seconds() -> int:
    return int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "28800"))


def _users() -> dict[str, dict[str, str]]:
    return {
        os.getenv("ADMIN_USERNAME", "admin"): {
            "password": os.getenv("ADMIN_PASSWORD", "admin"),
            "role": "admin",
        },
        os.getenv("USER_USERNAME", "user"): {
            "password": os.getenv("USER_PASSWORD", "user"),
            "role": "user",
        },
    }


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _signature(payload: str) -> str:
    digest = hmac.new(
        _token_secret().encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": int(time.time()) + _token_ttl_seconds(),
    }
    encoded_payload = _b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    return f"{encoded_payload}.{_signature(encoded_payload)}"


def _parse_token(token: str) -> AuthenticatedUser:
    try:
        encoded_payload, received_signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный токен авторизации",
        ) from exc

    expected_signature = _signature(encoded_payload)
    if not hmac.compare_digest(received_signature, expected_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный токен авторизации",
        )

    try:
        payload = json.loads(_b64decode(encoded_payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный токен авторизации",
        ) from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Срок действия токена истек",
        )

    username = payload.get("sub")
    role = payload.get("role")
    if not isinstance(username, str) or role not in {"user", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Некорректный токен авторизации",
        )
    return AuthenticatedUser(username=username, role=role)


@router.post("/login", response_model=AuthResponse, summary="Войти по логину и паролю")
async def login(payload: LoginRequest) -> AuthResponse:
    user = _users().get(payload.username)
    if user is None or not hmac.compare_digest(payload.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )

    token = _create_token(payload.username, user["role"])
    return AuthResponse(
        access_token=token,
        username=payload.username,
        role=user["role"],
        expires_in=_token_ttl_seconds(),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
        )
    if credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Поддерживается только Bearer токен",
        )
    return _parse_token(credentials.credentials)


async def require_admin(
    user: AuthenticatedUser = Depends(get_current_user),
) -> AuthenticatedUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Для операции нужны права администратора",
        )
    return user


@router.get("/me", response_model=CurrentUserResponse, summary="Текущий пользователь")
async def get_me(user: AuthenticatedUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(username=user.username, role=user.role)
