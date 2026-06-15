import secrets

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

_FIXED_USERNAME = "jason"
_FIXED_PASSWORD = "youaregood"


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


class CurrentUserResponse(BaseModel):
    username: str


def _tokens(request: Request) -> set[str]:
    tokens = getattr(request.app.state, "auth_tokens", None)
    if tokens is None:
        tokens = set()
        request.app.state.auth_tokens = tokens
    return tokens


def _bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return token


def is_valid_token(request: Request, token: str) -> bool:
    return token in _tokens(request)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request):
    username_ok = secrets.compare_digest(payload.username, _FIXED_USERNAME)
    password_ok = secrets.compare_digest(payload.password, _FIXED_PASSWORD)
    if not username_ok or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = secrets.token_urlsafe(32)
    _tokens(request).add(token)
    return LoginResponse(token=token, username=_FIXED_USERNAME)


@router.get("/me", response_model=CurrentUserResponse)
async def me(request: Request):
    token = _bearer_token(request)
    if not is_valid_token(request, token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return CurrentUserResponse(username=_FIXED_USERNAME)


@router.post("/logout")
async def logout(request: Request):
    try:
        token = _bearer_token(request)
    except HTTPException:
        return {"status": "ok"}
    _tokens(request).discard(token)
    return {"status": "ok"}
