"""create refresh tokens table

Revision ID: d28ff2a3e5ad
Revises: ded6d1c56730
Create Date: 2026-10-05 12:17:37.346444
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d28ff2a3e5ad"
down_revision: Union[str, Sequence[str], None] = "ded6d1c56730"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create refresh_tokens table."""

    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "token_hash",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )

    op.create_index(
        "ix_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Drop refresh_tokens table."""

    op.drop_index(
        "ix_refresh_tokens_token_hash",
        table_name="refresh_tokens",
    )

    op.drop_index(
        "ix_refresh_tokens_user_id",
        table_name="refresh_tokens",
    )

    op.drop_table("refresh_tokens")