from __future__ import annotations

import json
from datetime import datetime, timezone

from typer.testing import CliRunner

from memory_as_contracts.cli import app
from memory_as_contracts.models import (
    Contract,
    ContractKind,
    ContractSource,
    EdgeRelation,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleSemantics,
    Scope,
    ScopeLevel,
    SourceKind,
)
from memory_as_contracts.store import ContractStore


def test_mac_help_uses_new_package_identity() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Memory-as-Contracts" in result.output


def test_diagnostic_commands_are_registered() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "action-log",
        "search-actions",
        "asks",
    ):
        assert command in result.stdout


def test_env_reads_mac_variables(monkeypatch) -> None:
    monkeypatch.setenv("MAC_LLM_MODEL", "test-model")
    monkeypatch.setenv("MAC_DB_PATH", ".mac/test.sqlite")

    result = CliRunner().invoke(app, ["env", "--json"])

    assert result.exit_code == 0
    assert '"llm_model": "test-model"' in result.output
    assert '"db_path": ".mac/test.sqlite"' in result.output


def test_mac_rule_override_creates_override_edge(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "contracts.sqlite"
    monkeypatch.setenv("MAC_DB_PATH", str(db_path))
    store = ContractStore(db_path)
    store.init_db()
    store.add_contract(
        Contract(
            id="MAC-block",
            text="Do not push code.",
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            source=ContractSource(
                kind=SourceKind.USER_TURN,
                created_at=datetime(2026, 5, 23, tzinfo=timezone.utc),
            ),
            scope=Scope(
                level=ScopeLevel.PROJECT,
                workspace="/workspace/project",
                project="project",
            ),
            lifecycle=Lifecycle(
                type=LifecycleType.UNTIL_REVOKED,
                until_revoked=True,
            ),
            semantics=RuleSemantics(actions=["git.push"]),
        )
    )

    result = CliRunner().invoke(
        app,
        [
            "mac_rule_override",
            "MAC-block",
            "--scope-json",
            json.dumps(
                {
                    "level": "project",
                    "workspace": "/workspace/project",
                        "project": "project",
                }
            ),
            "--lifecycle-json",
            json.dumps({"type": "bounded_task"}),
            "--reason",
            "user approved this single action",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["to_contract"] == "MAC-block"
    assert payload["relation"] == EdgeRelation.OVERRIDE.value
    assert store.list_edges()[0].relation == EdgeRelation.OVERRIDE
