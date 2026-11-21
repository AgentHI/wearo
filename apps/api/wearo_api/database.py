from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine, make_url

SUPPORTED_DATABASE_DRIVERS = {"postgresql", "postgresql+psycopg"}


def normalize_database_url(value: str) -> URL:
    """Return a PostgreSQL URL that explicitly selects the installed psycopg 3 driver."""
    url = make_url(value)
    if url.drivername not in SUPPORTED_DATABASE_DRIVERS:
        raise ValueError("WEARO_DATABASE_URL must use PostgreSQL with the psycopg driver")
    if not url.database:
        raise ValueError("WEARO_DATABASE_URL must name a database")
    return url.set(drivername="postgresql+psycopg")


def create_database_engine(
    value: str,
    *,
    application_name: str,
    pool_size: int,
    max_overflow: int = 0,
    pool_timeout_seconds: int = 10,
) -> Engine:
    """Create a labelled, bounded PostgreSQL pool for one application process."""
    if not application_name.strip():
        raise ValueError("database application name is required")
    if pool_size < 1:
        raise ValueError("database pool size must be positive")
    if max_overflow < 0:
        raise ValueError("database pool overflow cannot be negative")
    if pool_timeout_seconds < 1:
        raise ValueError("database pool timeout must be positive")
    return create_engine(
        normalize_database_url(value),
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout_seconds,
        pool_use_lifo=True,
        connect_args={"application_name": application_name},
    )
