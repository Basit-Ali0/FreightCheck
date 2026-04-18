# backend/src/freightcheck/settings.py
"""Application configuration loaded from environment per Implementation Rules section 2.5.

`settings` is a module-level singleton. Importers must never read `os.environ`
directly — all env access flows through `Settings`.
"""

from typing import Annotated, Any, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Typed environment-backed settings.

    Fields with defaults are optional in `.env`. Fields without defaults
    (`MONGODB_URI`, `GEMINI_API_KEY`) are required at import time unless the
    caller is in a test context that patches them.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # API
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_allowed_origins(cls, value: Any) -> Any:
        """Accept CSV in `.env` (`a,b,c`) as well as JSON arrays and Python lists.

        Pydantic-settings v2 parses `list[str]` fields as JSON by default,
        which breaks the documented `.env` idiom `ALLOWED_ORIGINS=http://…`.
        """
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return stripped
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    MAX_FILE_SIZE_MB: int = 10

    # Mongo
    MONGODB_URI: str = ""
    MONGODB_DB: str = "freightcheck"

    # Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_MAX_RETRIES: int = 2

    # Agent budgets
    AGENT_MAX_ITERATIONS: int = 8
    AGENT_TOKEN_BUDGET: int = 50_000
    AGENT_TIME_BUDGET_MS: int = 25_000

    # Upload cache
    UPLOAD_CACHE_TTL_SECONDS: int = 600

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"


settings = Settings()
