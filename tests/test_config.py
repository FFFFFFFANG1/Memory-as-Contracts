from __future__ import annotations

from pathlib import Path

from memory_use_contracts.config import load_settings


def test_load_settings_from_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-key",
                "OPENAI_BASE_URL=http://localhost:9999/v1",
                "MUC_LLM_MODEL=test-model",
                "MUC_DB_PATH=.tmp/contracts.sqlite",
            ]
        )
    )

    settings = load_settings(env_path)

    assert settings.openai_api_key == "test-key"
    assert settings.openai_base_url == "http://localhost:9999/v1"
    assert settings.llm_model == "test-model"
    assert settings.db_path == Path(".tmp/contracts.sqlite")
