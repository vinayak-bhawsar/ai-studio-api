"""remove refresh tokens table

Revision ID: c8c07b7129ef
Revises: 09e115aee84b
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8c07b7129ef"
down_revision: Union[str, Sequence[str], None] = "09e115aee84b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("refresh_tokens")


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade for removing refresh_tokens is not supported."
    )