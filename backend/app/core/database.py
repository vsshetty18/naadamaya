"""
NAADAMAYA database connection.

- One SQLAlchemy engine and session factory for the whole app.
- get_db() is the FastAPI dependency: one session per request, committed
  when the request succeeds, rolled back when it fails.
- session_scope() is the same thing for code outside a request
  (the Celery worker, scripts).
"""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,   # drops dead connections instead of failing on them
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,    # refresh connections every 30 minutes
    echo=False,           # never echo SQL: queries can contain personal data
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency. Commits on success, rolls back on any error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """For the worker and scripts: commits on success, rolls back on error."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database() -> bool:
    """Used by the /health/db endpoint."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
