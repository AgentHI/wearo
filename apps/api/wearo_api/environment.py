from __future__ import annotations

import os

from dotenv import dotenv_values, find_dotenv, load_dotenv

NON_LOCAL_ENVIRONMENTS = {"production", "staging", "test"}


def load_wearo_environment() -> None:
    """Load local configuration with an explicit, opt-in dotenv precedence rule."""
    environment = os.environ.get("WEARO_ENVIRONMENT", "local").strip().casefold()
    if environment in NON_LOCAL_ENVIRONMENTS:
        return
    dotenv_path = find_dotenv(usecwd=True)
    if not dotenv_path:
        return
    dotenv_configuration = dotenv_values(dotenv_path)
    override = (
        str(dotenv_configuration.get("WEARO_LOCAL_DOTENV_OVERRIDE", "false")).casefold() == "true"
    )
    load_dotenv(dotenv_path, override=override)
