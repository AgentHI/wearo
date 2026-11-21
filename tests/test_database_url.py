from typing import Any

import pytest

from apps.api.wearo_api import database
from apps.api.wearo_api.database import create_database_engine, normalize_database_url


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


def test_database_engine_has_a_labelled_bounded_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    expected = object()

    def fake_create_engine(url: object, **options: object) -> object:
        captured["url"] = url
        captured.update(options)
        return expected

    monkeypatch.setattr(database, "create_engine", fake_create_engine)

    engine = create_database_engine(
        "postgresql://user:password@localhost/wearo",
        application_name="wearo-test",
        pool_size=3,
        max_overflow=2,
    )

    assert engine is expected
    assert captured["pool_size"] == 3
    assert captured["max_overflow"] == 2
    assert captured["pool_timeout"] == 10
    assert captured["pool_use_lifo"] is True
    assert captured["connect_args"] == {"application_name": "wearo-test"}


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"application_name": "", "pool_size": 1}, "application name"),
        ({"application_name": "test", "pool_size": 0}, "pool size"),
        (
            {"application_name": "test", "pool_size": 1, "max_overflow": -1},
            "overflow",
        ),
    ],
)
def test_database_engine_rejects_invalid_pool_configuration(
    options: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        create_database_engine("postgresql://user:password@localhost/wearo", **options)  # type: ignore[arg-type]
