"""
NAADAMAYA Alembic environment.

- The database URL comes from the app settings (DATABASE_URL), not alembic.ini.
- Every module in app/models is imported so Alembic sees all tables.
"""

import importlib
import pkgutil
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# One source of truth for the database address.
config.set_main_option("sqlalchemy.url", settings.database_url)


def _import_all_models() -> None:
    """Imports every module in app.models so its tables register on Base.metadata."""
    package = importlib.import_module("app.models")
    for module in pkgutil.iter_modules(package.__path__):
        importlib.import_module(f"app.models.{module.name}")


_import_all_models()

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generates SQL without connecting to the database."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Runs migrations against the real database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
