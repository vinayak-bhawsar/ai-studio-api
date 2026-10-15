from logging.config import fileConfig
import sys
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context


# ---------------------------------------------------------
# Add project root to Python path
# ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------
# Import application configuration and SQLAlchemy Base
# ---------------------------------------------------------
from app.core.config import settings
from app.core.database import Base


# ---------------------------------------------------------
# Import ALL SQLAlchemy models
#
# These imports are required so that every model registers
# its table inside Base.metadata before Alembic performs
# autogeneration / schema comparison.
# ---------------------------------------------------------
from app.models.user import User
from app.models.project import Project
from app.models.conversation import Conversation
from app.models.message import Message

from app.models.screenplay import (
    Screenplay,
    ScreenplayVersion,
)

from app.models.stylebook import StyleBook
from app.models.character import Character
from app.models.environment import Environment
from app.models.scene import Scene
from app.models.shot import Shot


# ---------------------------------------------------------
# Alembic Config
# ---------------------------------------------------------
config = context.config


# ---------------------------------------------------------
# Set database URL from .env
# ---------------------------------------------------------
config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL.replace("%", "%%"),
)


# ---------------------------------------------------------
# Metadata for Alembic autogenerate
# ---------------------------------------------------------
target_metadata = Base.metadata


# ---------------------------------------------------------
# Offline migrations
# ---------------------------------------------------------
def run_migrations_offline() -> None:
    """
    Run migrations without creating a database connection.
    """

    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------
# Online migrations
# ---------------------------------------------------------
def run_migrations_online() -> None:
    """
    Run migrations using an actual database connection.
    """

    connectable = engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------
# Run migration
# ---------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()