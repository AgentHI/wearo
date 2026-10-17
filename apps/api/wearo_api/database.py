from __future__ import annotations

from sqlalchemy.engine import URL, make_url

SUPPORTED_DATABASE_DRIVERS = {"postgresql", "postgresql+psycopg"}


def normalize_database_url(value: str) -> URL:
    """Return a PostgreSQL URL that explicitly selects the installed psycopg 3 driver."""
    url = make_url(value)
    if url.drivername not in SUPPORTED_DATABASE_DRIVERS:
        raise ValueError("WEARO_DATABASE_URL must use PostgreSQL with the psycopg driver")
    if not url.database:
        raise ValueError("WEARO_DATABASE_URL must name a database")
    return url.set(drivername="postgresql+psycopg")
