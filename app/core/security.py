from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.repository.user_repo import get_user_by_id


password_hash = PasswordHash.recommended()

bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a user password."""

    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Verify a password."""

    return password_hash.verify(
        plain_password,
        hashed_password,
    )


def create_access_token(
    user_id: str,
) -> str:
    """Create a short-lived access token."""

    now = datetime.now(timezone.utc)

    expire = now + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
) -> dict[str, Any]:
    """Decode and validate an access token."""

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        if payload.get("type") != "access":
            raise ValueError("Invalid token type")

        return payload

    except JWTError as exc:
        raise ValueError(
            "Invalid or expired access token"
        ) from exc


def create_refresh_token(
    user_id: str,
) -> str:
    """Create a stateless refresh JWT."""

    now = datetime.now(timezone.utc)

    expire = now + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )

    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_refresh_token(
    token: str,
) -> dict[str, Any]:
    """Decode and validate a refresh token."""

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")

        return payload

    except JWTError as exc:
        raise ValueError(
            "Invalid or expired refresh token"
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
):
    """Return the authenticated user from the access token."""

    try:
        payload = decode_access_token(
            credentials.credentials
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={
                "WWW-Authenticate": "Bearer"
            },
        ) from exc

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    user = get_user_by_id(
        db,
        user_id,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    return user