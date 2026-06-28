from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class MacConfig:
    openai_api_key: str | None
    openai_base_url: str | None
    llm_model: str | None
    llm_max_tokens: int
    db_path: Path
    llm_timeout_seconds: float
    log_path: Path
    log_level: str


def load_config(env_file: str | Path | None = None) -> MacConfig:
    """Load MAC configuration from `.env` and process environment variables."""

    if env_file is not None:
        load_dotenv(env_file, override=True)
    else:
        load_dotenv()

    return MacConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
        llm_model=os.getenv("MAC_LLM_MODEL"),
        llm_max_tokens=int(os.getenv("MAC_LLM_MAX_TOKENS", "4096")),
        db_path=Path(os.getenv("MAC_DB_PATH", ".mac/contracts.sqlite")),
        llm_timeout_seconds=float(os.getenv("MAC_LLM_TIMEOUT_SECONDS", "60")),
        log_path=Path(os.getenv("MAC_LOG_PATH", ".mac/mac.log")),
        log_level=os.getenv("MAC_LOG_LEVEL", "INFO"),
    )
