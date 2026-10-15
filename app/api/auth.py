from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshTokenResponse,
    RegisterRequest,
    UserResponse,
)
from app.schemas.response import APIResponse
from app.service.auth_service import (
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
) -> APIResponse[UserResponse]:
    """Register a new user."""

    user = register_user(
        db,
        data,
    )

    return APIResponse(
        success=True,
        message="User registered successfully.",
        data=user,
    )


@router.post(
    "/login",
    response_model=APIResponse[LoginResponse],
)
def login(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> APIResponse[LoginResponse]:
    """Authenticate a user."""

    login_response, refresh_token = login_user(
        db,
        data,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=(
            settings.REFRESH_TOKEN_EXPIRE_DAYS
            * 24
            * 60
            * 60
        ),
    )

    return APIResponse(
        success=True,
        message="Login successful.",
        data=login_response,
    )


@router.post(
    "/refresh",
    response_model=APIResponse[RefreshTokenResponse],
)
def refresh(
    refresh_token: str | None = Cookie(
        default=None,
    ),
    db: Session = Depends(get_db),
) -> APIResponse[RefreshTokenResponse]:
    """Refresh the access token."""

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is missing.",
        )

    token_response = refresh_access_token(
        db,
        refresh_token,
    )

    return APIResponse(
        success=True,
        message="Token refreshed successfully.",
        data=token_response,
    )


@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
)
def get_me(
    current_user: User = Depends(
        get_current_user
    ),
) -> APIResponse[UserResponse]:
    """Return the currently authenticated user."""

    user = UserResponse(
        id=str(current_user.id),
        email=current_user.email,
    )

    return APIResponse(
        success=True,
        message="User fetched successfully.",
        data=user,
    )


@router.post(
    "/logout",
    response_model=APIResponse[None],
)
def logout(
    response: Response,
) -> APIResponse[None]:
    """Logout the current user."""

    logout_user()

    response.delete_cookie(
        key="refresh_token",
    )

    return APIResponse(
        success=True,
        message="Logout successful.",
        data=None,
    )