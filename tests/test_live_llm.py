from __future__ import annotations

import os

import pytest

from memory_use_contracts.config import load_settings
from memory_use_contracts.extractor import ContractExtractor
from memory_use_contracts.models import ContractType, SourceKind


@pytest.mark.live_llm
def test_live_extractor_handles_project_instructions() -> None:
    if os.getenv("MUC_RUN_LIVE_TESTS") != "1":
        pytest.skip("set MUC_RUN_LIVE_TESTS=1 to run live LLM tests")

    settings = load_settings()
    if not settings.openai_api_key:
        pytest.skip("OPENAI_API_KEY is not configured")

    contracts = ContractExtractor(settings).extract(
        (
            "In this repo, do not edit vendor/**. "
            "Always run uv run pytest before finishing."
        ),
        source_kind=SourceKind.PROJECT_DOC,
        workspace="live-test",
    )

    assert len(contracts) >= 2
    assert any(contract.type == ContractType.PROHIBITION for contract in contracts)
    assert any("uv" in contract.text.lower() for contract in contracts)
