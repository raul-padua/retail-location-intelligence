"""Environment-variable configuration. No credential ever appears in source."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

DEFAULT_LLM_MODEL = "gpt-5.6-luna"
"""Cost-tier current-generation model.

The LLM's job here is narrow - rewrite a fact sheet, answer questions about facts it was
handed - and its output is verified against the evidence either way, so paying for
frontier reasoning buys very little. Overridable via ``RLI_LLM_MODEL`` or in the UI.
"""


class MissingTokenError(RuntimeError):
    """Raised when no Atlas token is configured.

    Carried as an explicit error type so the UI can render an actionable setup message
    rather than a stack trace, and so the missing-token test case has something to assert.
    """


@dataclass(frozen=True)
class Settings:
    atlas_token: str | None
    atlas_base_url: str
    timeout_seconds: float
    max_retries: int
    openai_api_key: str | None
    llm_model: str
    log_level: str

    def require_token(self) -> str:
        if not self.atlas_token or not self.atlas_token.strip():
            raise MissingTokenError(
                "STATEBOOK_API_TOKEN is not set. Copy .env.example to .env and set "
                "STATEBOOK_API_TOKEN=demo to use the public evaluation token."
            )
        return self.atlas_token.strip()

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    def with_llm(self, api_key: str | None, model: str | None = None) -> Settings:
        """Return a copy carrying a session-supplied key and model.

        The UI collects the key at runtime rather than requiring a ``.env`` edit. It is
        held in Streamlit session state for the life of the browser session and is never
        written to disk, logged, or included in an exported result.
        """
        cleaned_key = (api_key or "").strip() or None
        cleaned_model = (model or "").strip() or self.llm_model
        return replace(self, openai_api_key=cleaned_key, llm_model=cleaned_model)

    @property
    def is_demo_token(self) -> bool:
        return (self.atlas_token or "").strip().lower() == "demo"


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def load_settings() -> Settings:
    return Settings(
        atlas_token=os.getenv("STATEBOOK_API_TOKEN"),
        atlas_base_url=os.getenv("STATEBOOK_API_BASE_URL", "https://api.statebook.com").rstrip("/"),
        timeout_seconds=_float_env("STATEBOOK_TIMEOUT_SECONDS", 30.0),
        max_retries=max(0, min(_int_env("STATEBOOK_MAX_RETRIES", 2), 5)),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        llm_model=os.getenv("RLI_LLM_MODEL", DEFAULT_LLM_MODEL),
        log_level=os.getenv("RLI_LOG_LEVEL", "INFO").upper(),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
