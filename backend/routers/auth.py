"""Authentication endpoints — login, token refresh, and current-user profile."""

import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.graph import User
from schemas.graph import LoginRequest, TokenResponse, UserRead

router = APIRouter()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()

_SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey123")
_ALGORITHM = "HS256"
_EXPIRE_MINUTES = 60


# ── Shared dependency ─────────────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the Bearer JWT and return the corresponding User row.

    Raises HTTP 401 if the token is missing, malformed, expired, or if the
    encoded user no longer exists in the database.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, _SECRET_KEY, algorithms=[_ALGORITHM])
        user_id: str = payload.get("sub", "")
        if not user_id:
            raise invalid
    except JWTError:
        raise invalid

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise invalid
    return user


# ── Helpers ───────────────────────────────────────────────────────────────────


def _issue_token(user_id: uuid.UUID) -> TokenResponse:
    """Sign and return a fresh JWT for *user_id*."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": str(user_id), "exp": expire},
        _SECRET_KEY,
        algorithm=_ALGORITHM,
    )
    return TokenResponse(access_token=token, expires_in=_EXPIRE_MINUTES * 60)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT access token",
    responses={
        401: {"description": "Invalid email or password"},
        422: {"description": "Validation error — invalid request body"},
    },
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Validate credentials and return a signed JWT access token.

    The token encodes ``sub`` = user UUID (string) and expires after 60 minutes.
    Pass it as ``Authorization: Bearer <token>`` on protected routes.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not _pwd_context.verify(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _issue_token(user.id)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a valid JWT for a new one with a refreshed expiry",
    responses={
        401: {"description": "Token is missing, malformed, or expired"},
    },
)
async def refresh(
    current_user: User = Depends(get_current_user),
) -> TokenResponse:
    """Return a new JWT with a fresh 60-minute expiry.

    The caller must supply their current (not yet expired) token as
    ``Authorization: Bearer <token>``.  The old token is not revoked — token
    revocation requires a deny-list backed by Redis, which is out of scope here.
    """
    return _issue_token(current_user.id)


@router.get(
    "/me",
    response_model=UserRead,
    summary="Return the profile of the currently authenticated user",
    responses={
        401: {"description": "Token is missing, malformed, or expired"},
    },
)
async def me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the full public profile for the token's owner."""
    return current_user
