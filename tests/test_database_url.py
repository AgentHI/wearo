import pytest

from apps.api.wearo_api.database import normalize_database_url


def test_plain_postgresql_url_selects_psycopg_three() -> None:
    url = normalize_database_url("postgresql://user:password@127.0.0.1:5432/database")
    assert url.drivername == "postgresql+psycopg"
    assert url.database == "database"


def test_explicit_psycopg_url_is_supported() -> None:
    url = normalize_database_url("postgresql+psycopg://user:password@localhost/database")
    assert url.drivername == "postgresql+psycopg"


def test_digitalocean_sslmode_is_preserved() -> None:
    url = normalize_database_url(
        "postgresql://doadmin:password@db.example.com:25060/defaultdb?sslmode=require"
    )

    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"


@pytest.mark.parametrize(
    "value",
    ["sqlite:///wearo.db", "mysql://user:password@localhost/wearo"],
)
def test_non_postgresql_driver_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="must use PostgreSQL"):
        normalize_database_url(value)
