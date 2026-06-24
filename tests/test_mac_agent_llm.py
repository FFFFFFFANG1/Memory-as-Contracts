import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bench.MAC.agent.llm import LLMConfig, OpenAIChatModelClient


def _message(content: str = "") -> SimpleNamespace:
    return SimpleNamespace(content=content, tool_calls=[], reasoning_content=None)


def test_openai_client_retries_empty_choices() -> None:
    empty = SimpleNamespace(choices=[], model="test-model", id="resp-empty")
    ok = SimpleNamespace(
        choices=[SimpleNamespace(message=_message("done"))],
        usage=None,
        model="test-model",
        id="resp-ok",
    )
    create = AsyncMock(side_effect=[empty, ok])
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    client = OpenAIChatModelClient(LLMConfig(model="test-model", api_key_env="OPENAI_API_KEY"))
    client._client = fake_client

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        response = asyncio.run(client(messages=[{"role": "user", "content": "hi"}], tools=[]))

    assert response["content"] == "done"
    assert create.await_count == 2


def test_openai_client_raises_clear_error_after_empty_choices_exhausted() -> None:
    empty = SimpleNamespace(choices=[], model="test-model", id="resp-empty")
    create = AsyncMock(return_value=empty)
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    client = OpenAIChatModelClient(LLMConfig(model="test-model", api_key_env="OPENAI_API_KEY"), max_retries=2)
    client._client = fake_client

    with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
        with pytest.raises(RuntimeError, match="LLM request failed after 2 attempts"):
            asyncio.run(client(messages=[{"role": "user", "content": "hi"}], tools=[]))

    assert create.await_count == 2
