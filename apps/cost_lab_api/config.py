from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from apps.api.wearo_api.database import normalize_database_url
from apps.api.wearo_api.environment import load_wearo_environment


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_username: str
    password_hash: str
    session_secret: str
    encryption_key: str
    session_ttl_minutes: int
    secure_cookie: bool
    storage_root: Path
    fx_url: str
    storage_backend: str = "FILESYSTEM"
    storage_bucket: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        load_wearo_environment()
        required = {
            "WEARO_DATABASE_URL": os.getenv("WEARO_DATABASE_URL", ""),
            "COST_LAB_ADMIN_USERNAME": os.getenv("COST_LAB_ADMIN_USERNAME", ""),
            "COST_LAB_ADMIN_PASSWORD_HASH": os.getenv("COST_LAB_ADMIN_PASSWORD_HASH", ""),
            "COST_LAB_SESSION_SECRET": os.getenv("COST_LAB_SESSION_SECRET", ""),
            "COST_LAB_ENCRYPTION_KEY": os.getenv("COST_LAB_ENCRYPTION_KEY", ""),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing Cost Lab configuration: {', '.join(missing)}")
        return cls(
            database_url=normalize_database_url(required["WEARO_DATABASE_URL"]).render_as_string(
                hide_password=False
            ),
            admin_username=required["COST_LAB_ADMIN_USERNAME"],
            password_hash=required["COST_LAB_ADMIN_PASSWORD_HASH"],
            session_secret=required["COST_LAB_SESSION_SECRET"],
            encryption_key=required["COST_LAB_ENCRYPTION_KEY"],
            session_ttl_minutes=int(os.getenv("COST_LAB_SESSION_TTL_MINUTES", "60")),
            secure_cookie=os.getenv("COST_LAB_SECURE_COOKIE", "true").lower() == "true",
            storage_root=Path(os.getenv("COST_LAB_STORAGE_ROOT", ".wearo-storage/cost-lab")),
            storage_backend=os.getenv("COST_LAB_STORAGE_BACKEND", "FILESYSTEM").strip().upper(),
            storage_bucket=os.getenv("COST_LAB_STORAGE_BUCKET", ""),
            fx_url=os.getenv(
                "COST_LAB_FX_URL", "https://api.frankfurter.app/latest?from=USD&to=INR"
            ),
        )
