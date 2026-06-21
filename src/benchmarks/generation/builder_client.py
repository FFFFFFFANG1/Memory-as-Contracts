from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI


class JsonBuilder(Protocol):
    def generate_json(self, *, system_prompt: str, user_prompt: str, response_name: str) -> dict: ...


@dataclass(frozen=True)
class BuilderConfig:
    model: str
    api_key: str
    base_url: str | None = None


def load_builder_config(env_file: str | None = None) -> BuilderConfig:
    load_dotenv(env_file, override=False)
    model = os.getenv("BENCH_BUILDER_MODEL")
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
    if not model:
        raise ValueError("BENCH_BUILDER_MODEL is required for benchmark build generation")
    if not api_key:
        raise ValueError("OPENAI_API_KEY or LLM_API_KEY is required for benchmark build generation")
    return BuilderConfig(model=model, api_key=api_key, base_url=base_url)


class OpenAIJsonBuilder:
    def __init__(self, config: BuilderConfig | None = None) -> None:
        self.config = config or load_builder_config()
        self.client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)

    def generate_json(self, *, system_prompt: str, user_prompt: str, response_name: str) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except BadRequestError as exc:
            if "response_format" not in str(exc):
                raise
            response = self.client.chat.completions.create(
                model=self.config.model,
                temperature=0,
                messages=messages,
            )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError(f"{response_name} builder returned empty content")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{response_name} builder returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{response_name} builder must return a JSON object")
        return payload
