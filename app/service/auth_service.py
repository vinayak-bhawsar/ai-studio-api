from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.repository.user_repo import (
    create_user,
    get_user_by_email,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenResponse,
    RegisterRequest,
    UserResponse,
)


def register_user(
    db: Session,
    data: RegisterRequest,
) -> UserResponse:
    """Register a new user."""

    existing_user = get_user_by_email(
        db,
        data.email,
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        )

    password_hash_value = hash_password(
        data.password
    )

    user = create_user(
        db,
        email=data.email,
        password_hash=password_hash_value,
    )

    return UserResponse(
        id=str(user.id),
        email=user.email,
    )


def login_user(
    db: Session,
    data: LoginRequest,
) -> tuple[LoginResponse, str]:
    """Authenticate user and create access/refresh tokens."""

    user = get_user_by_email(
        db,
        data.email,
    )

    if not user or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    access_token = create_access_token(
        str(user.id)
    )

    refresh_token = create_refresh_token(
        str(user.id)
    )

    response = LoginResponse(
        access_token=access_token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
        ),
    )

    return response, refresh_token


def refresh_access_token(
    db: Session,
    refresh_token: str,
) -> RefreshTokenResponse:
    """Validate a stateless refresh token and create a new access token."""

    try:
        payload = decode_refresh_token(
            refresh_token
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    access_token = create_access_token(
        str(user_id)
    )

    return RefreshTokenResponse(
        access_token=access_token,
    )


def logout_user() -> None:
    """Logout is handled by deleting the refresh-token cookie."""