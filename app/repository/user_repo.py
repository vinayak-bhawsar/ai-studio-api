import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_user_by_email(
    db: Session,
    email: str,
) -> User | None:
    """Return a user by email."""

    statement = select(User).where(
        User.email == email
    )

    return db.scalar(statement)


def get_user_by_id(
    db: Session,
    user_id: str,
) -> User | None:
    """Return a user by ID."""

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return None

    statement = select(User).where(
        User.id == user_uuid
    )

    return db.scalar(statement)


def create_user(
    db: Session,
    *,
    email: str,
    password_hash: str,
) -> User:
    """Create and persist a user."""

    user = User(
        email=email,
        password_hash=password_hash,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user