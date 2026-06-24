"""LLM client adapters for MAC agent evaluation."""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class LLMConfig:
    model: str
    base_url: str | None = None
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.0
    max_tokens: int = 4096

    def to_metadata(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key_set"] = bool(os.getenv(self.api_key_env))
        return data


class DryRunModelClient:
    """Model client that immediately submits a terminal dry-run answer."""

    def __init__(self, answer_prefix: str = "[dry-run]") -> None:
        self.answer_prefix = answer_prefix

    async def __call__(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        user_prompt = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content")
                if isinstance(content, str):
                    user_prompt = content
                    break
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "dry_run_send_message",
                    "type": "function",
                    "function": {
                        "name": "send_message",
                        "arguments": {
                            "response": f"{self.answer_prefix} Prepared loop input for: {user_prompt[:160]}"
                        },
                    },
                }
            ],
        }


class OpenAIChatModelClient:
    """OpenAI-compatible chat completions client."""

    def __init__(self, config: LLMConfig, *, max_retries: int = 3) -> None:
        self.config = config
        self.max_retries = max(1, max_retries)
        self._client: Any | None = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client

        from openai import AsyncOpenAI

        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing API key env var: {self.config.api_key_env}")
        self._client = AsyncOpenAI(api_key=api_key, base_url=self.config.base_url)
        return self._client

    @staticmethod
    def _empty_choices_detail(response: Any) -> str:
        if hasattr(response, "model_dump"):
            payload = response.model_dump(exclude_none=True)
            for key in ("id", "model", "error", "message"):
                value = payload.get(key)
                if value:
                    return f"{key}={value!r}"
            return str(payload)[:500]
        return repr(response)[:500]

    async def __call__(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        client = self._client_or_raise()
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    tools=tools or None,
                    tool_choice="auto" if tools else None,
                    temperature=self.config.temperature,
                    max_tokens=self.config.max_tokens,
                )
                choices = getattr(response, "choices", None)
                if not choices:
                    detail = self._empty_choices_detail(response)
                    raise RuntimeError(
                        "LLM returned no choices "
                        f"(model={self.config.model}, attempt={attempt}/{self.max_retries}, {detail})"
                    )

                message = choices[0].message
                tool_calls = []
                for call in message.tool_calls or []:
                    tool_calls.append(
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                    )
                return {
                    "content": message.content or "",
                    "reasoning_content": getattr(message, "reasoning_content", None),
                    "tool_calls": tool_calls,
                    "usage": response.usage.model_dump() if response.usage else {},
                }
            except Exception as exc:  # noqa: BLE001 - retry provider/transport failures.
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(min(2.0 * attempt, 8.0))

        if last_error is not None:
            raise RuntimeError(
                f"LLM request failed after {self.max_retries} attempts "
                f"(model={self.config.model}): {last_error}"
            ) from last_error
        raise RuntimeError(f"LLM request failed after {self.max_retries} attempts (model={self.config.model})")


def model_client_from_config(config: LLMConfig, *, dry_run: bool = False):
    if dry_run:
        return DryRunModelClient()
    return OpenAIChatModelClient(config)
