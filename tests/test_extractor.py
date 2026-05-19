from __future__ import annotations

import pytest
from openai import APIConnectionError
import httpx

from memory_use_contracts.config import Settings
from memory_use_contracts.extractor import ContractExtractionError, ContractExtractor, parse_extraction_json
from memory_use_contracts.models import ActionClass, ContractType, SourceKind


def test_parse_extraction_json() -> None:
    contracts = parse_extraction_json(
        """
        {
          "contracts": [
            {
              "text": "Do not edit vendor files.",
              "type": "prohibition",
              "modality": "MUST_NOT",
              "source": {"span": "Do not edit vendor files."},
              "scope": {"path_globs": ["vendor/**"]},
              "action_classes": ["edit_file"],
              "strength": "soft",
              "confirmation": "required_to_override",
              "confidence": 0.9
            }
          ]
        }
        """,
        source_kind=SourceKind.USER_EXPLICIT,
    )

    assert len(contracts) == 1
    assert contracts[0].type == ContractType.PROHIBITION
    assert contracts[0].action_classes == [ActionClass.EDIT_FILE]


def test_parse_extraction_rejects_missing_contracts_array() -> None:
    with pytest.raises(ContractExtractionError, match="contracts"):
        parse_extraction_json("{}", source_kind=SourceKind.USER_EXPLICIT)


def test_parse_extraction_normalizes_common_llm_aliases() -> None:
    contracts = parse_extraction_json(
        """
        {
          "contracts": [
            {
              "text": "do not edit vendor/**",
              "type": "prohibition",
              "modality": "deontic",
              "source": {"span": "do not edit vendor/**"},
              "scope": "project",
              "action_classes": ["write_file"],
              "strength": "strict",
              "confirmation": "explicit",
              "confidence": "high"
            }
          ]
        }
        """,
        source_kind=SourceKind.PROJECT_DOC,
        workspace="demo",
    )

    assert contracts[0].modality.value == "MUST_NOT"
    assert contracts[0].strength.value == "hard"
    assert contracts[0].confirmation == "required_to_override"
    assert contracts[0].scope.workspace == "demo"
    assert contracts[0].scope.path_globs == ["vendor/**"]
    assert contracts[0].action_classes == [ActionClass.EDIT_FILE]
    assert contracts[0].confidence == 0.9


def test_parse_extraction_downgrades_spurious_confirmation_on_plain_prohibition() -> None:
    contracts = parse_extraction_json(
        """
        {
          "contracts": [
            {
              "text": "Do not edit generated/**",
              "type": "prohibition",
              "modality": "MUST_NOT",
              "source": {"span": "Do not edit generated/**"},
              "scope": {"path_globs": ["generated/**"]},
              "action_classes": ["edit_file"],
              "strength": "hard",
              "confirmation": "required",
              "confidence": 0.8
            }
          ]
        }
        """,
        source_kind=SourceKind.PROJECT_DOC,
        workspace="demo",
    )

    assert contracts[0].confirmation == "not_required"
    assert contracts[0].strength.value == "hard"


def test_extractor_wraps_openai_errors(monkeypatch) -> None:
    class FakeCompletions:
        def create(self, *args, **kwargs):
            request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
            raise APIConnectionError(request=request)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("memory_use_contracts.extractor.OpenAI", FakeClient)
    settings = Settings(
        openai_api_key="test-key",
        openai_base_url=None,
        llm_model="test-model",
        db_path=":memory:",
    )

    with pytest.raises(ContractExtractionError, match="LLM extraction failed"):
        ContractExtractor(settings).extract("Use uv.", SourceKind.PROJECT_DOC)
