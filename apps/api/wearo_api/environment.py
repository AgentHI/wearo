from __future__ import annotations

from dotenv import dotenv_values, find_dotenv, load_dotenv


def load_wearo_environment() -> None:
    """Load local configuration with an explicit, opt-in dotenv precedence rule."""
    dotenv_path = find_dotenv(usecwd=True)
    if not dotenv_path:
        return
    dotenv_configuration = dotenv_values(dotenv_path)
    override = (
        str(dotenv_configuration.get("WEARO_LOCAL_DOTENV_OVERRIDE", "false")).casefold() == "true"
    )
    load_dotenv(dotenv_path, override=override)
