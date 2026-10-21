"""Regressions for main-only integrations carried onto bench_v2."""

from __future__ import annotations

import pytest

from bench.MAC.agent.memory.mem0 import Mem0Config, _build_mem0_llm_config
from bench.MAC.construct.cctu.noise_eval_grade import build_contract_diagnostics
from bench.MAC.scripts.run_bm25_embedding_batch import grade_module


@pytest.mark.parametrize(
    ("enable", "disable", "expected"),
    [(None, None, False), (None, "false", True), ("false", "false", False),
     ("true", "true", True)],
)
def test_deepseek_provider_respects_explicit_thinking_override(
    monkeypatch, enable, disable, expected,
) -> None:
    for key, value in [("MEM_ENABLE_THINKING", enable), ("MEM_DISABLE_THINKING", disable)]:
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("MEM_LLM_MAX_TOKENS", "512")
    monkeypatch.setenv("MEM_REASONING_EFFORT", "minimal")
    result = _build_mem0_llm_config(
        mem_api_key="test-key",
        config=Mem0Config(mem_llm_model="deepseek-test", mem_base_url="https://example.test/v1"),
    )
    assert result["provider"] == "deepseek"
    assert result["config"]["enable_thinking"] is expected
    assert result["config"]["deepseek_base_url"] == "https://example.test/v1"
    assert result["config"]["max_tokens"] == 512


def test_non_deepseek_provider_keeps_openai_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("MEM_LLM_MAX_TOKENS", "256")
    result = _build_mem0_llm_config(
        mem_api_key="test-key",
        config=Mem0Config(mem_llm_model="other-model", mem_base_url="https://example.test/v1"),
    )
    assert result["provider"] == "openai"
    assert result["config"]["openai_base_url"] == "https://example.test/v1"
    assert result["config"]["max_tokens"] == 256
    assert "enable_thinking" not in result["config"]


def test_cctu_diagnostics_keep_legacy_counts_alongside_noise_rate() -> None:
    scores = build_contract_diagnostics([])["constraint_follow_scores"]
    assert scores["noise_follow_rate"] is None
    assert scores["outcome_counts"] == {
        "correct_follow": 0, "wrong_follow": 0, "neither_followed": 0,
    }
    populated = build_contract_diagnostics([{
        "follow_outcome": "correct_follow",
        "active_constraint_count": 1,
        "history_constraint_count": 2,
        "history_hit_count": 1,
    }])["constraint_follow_scores"]
    assert populated["noise_follow_rate"] == 0.5
    assert populated["outcome_counts"]["correct_follow"] == 1


def test_batch_runner_resolves_relocated_cctu_grader() -> None:
    import importlib

    module = importlib.import_module(grade_module("cctu"))
    assert callable(module.main)
