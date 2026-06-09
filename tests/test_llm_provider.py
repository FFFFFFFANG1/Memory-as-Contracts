from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_as_contracts.config import MacConfig
from memory_as_contracts.extractor import LLMCallError, OpenAIChatResponseProvider


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=outcome))]
        )


def provider_with(outcomes) -> tuple[OpenAIChatResponseProvider, FakeCompletions]:
    completions = FakeCompletions(outcomes)
    provider = object.__new__(OpenAIChatResponseProvider)
    provider.config = MacConfig(
        openai_api_key="test",
        openai_base_url=None,
        llm_model="test-model",
        db_path=Path(":memory:"),
        llm_timeout_seconds=1.0,
        log_path=Path("mac.log"),
        log_level="INFO",
    )
    provider.system_prompt = "system"
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    provider._sleep = lambda _seconds: None
    return provider, completions


def test_openai_provider_retries_timeouts_and_returns_third_attempt() -> None:
    provider, completions = provider_with(
        [TimeoutError("one"), TimeoutError("two"), "ok"]
    )

    assert provider("prompt") == "ok"
    assert completions.calls == 3


def test_openai_provider_returns_stable_error_after_three_timeouts() -> None:
    provider, completions = provider_with(
        [TimeoutError("one"), TimeoutError("two"), TimeoutError("three")]
    )

    with pytest.raises(LLMCallError) as caught:
        provider("prompt")

    assert caught.value.as_dict() == {
        "code": "llm_timeout",
        "message": "LLM request timed out after 3 attempts",
        "attempts": 3,
    }
    assert completions.calls == 3
