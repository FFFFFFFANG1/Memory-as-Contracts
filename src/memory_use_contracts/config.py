from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_base_url: str | None
    llm_model: str
    db_path: Path


def load_settings(env_path: str | Path = ".env") -> Settings:
    load_dotenv(env_path)
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_base_url=os.getenv("OPENAI_BASE_URL") or None,
        llm_model=os.getenv("MUC_LLM_MODEL") or "gpt-4.1-mini",
        db_path=Path(os.getenv("MUC_DB_PATH") or ".muc/contracts.sqlite"),
    )
