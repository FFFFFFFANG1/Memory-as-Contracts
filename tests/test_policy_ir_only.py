from __future__ import annotations

from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from bench.MAC.agent.memory.mac import MACMemoryConfig
from bench.MAC.scripts import run_memory_eval
from memory_as_contracts.cli import app
from memory_as_contracts.extractor import PolicyIRContractExtractor
from memory_as_contracts.gate import ActionGate
from memory_as_contracts.hook_plan import build_active_hook_plan
from memory_as_contracts.hook_runtime import _default_online_extractor_factory
from memory_as_contracts.models import Contract, Lifecycle, Scope, ToolPattern, ValidatorVersion
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext
from memory_as_contracts.store import ContractStore


def test_legacy_code_is_never_loaded_and_missing_policy_requires_migration(monkeypatch, tmp_path):
    store = ContractStore(":memory:")
    try:
        store.init_db()
        rule = store.add_contract(Contract(
            text="Do not run shell commands.", effect="deny",
            scope=Scope(level="session"),
            lifecycle=Lifecycle(type="until_revoked", until_revoked=True),
            check_patterns=[ToolPattern(tool="Bash")],
        ))
        marker = tmp_path / "executed"
        store.add_validator_version(ValidatorVersion(
            contract_id=rule.id, enforcement_shape="check_only",
            check_code=f"def check(action, log, context):\n    open({str(marker)!r}, 'w').write('executed')\n",
            check_patterns=[ToolPattern(tool="Bash")],
            snippet_hash="legacy", verification_hash="legacy",
        ))

        def forbidden_lookup(*args, **kwargs):
            pytest.fail("PolicyIR runtime consulted legacy Python validator versions")

        monkeypatch.setattr(store, "get_active_validator_version", forbidden_lookup)
        monkeypatch.setattr(store, "list_validator_versions", forbidden_lookup)
        signature = ActionSignatureBuilder().build(
            tool_name="Bash", raw_arguments={"command": "echo hello"},
            context=SignatureContext(
                host="codex", agent_family="codex", session_id="s", task_id="t",
                workspace=str(tmp_path), cwd=str(tmp_path),
                now=datetime(2026, 10, 21, tzinfo=timezone.utc),
            ),
        )
        plan = build_active_hook_plan(store, signature, active_paths=[])
        assert [entry.kind for entry in plan.current_active_prehook] == ["policy_missing"]
        result = ActionGate(store).gate(signature)
        assert result.decision.decision.value == "ask"
        assert "migrate" in result.decision.reason
        assert not marker.exists()
        assert store.get_contract(rule.id) is not None
    finally:
        store.close()


def test_default_adapter_extractor_is_policy_ir(monkeypatch):
    monkeypatch.setattr(
        "memory_as_contracts.extractor.OpenAIChatResponseProvider.from_env",
        lambda: (lambda prompt: '{"policies": []}'),
    )
    assert isinstance(_default_online_extractor_factory(), PolicyIRContractExtractor)


def test_unified_ops_stays_off_even_with_old_environment_toggle(monkeypatch):
    monkeypatch.setattr(run_memory_eval, "load_bench_env", lambda: None)
    monkeypatch.setenv("MAC_UNIFIED_OPS_EXTRACTION", "true")
    monkeypatch.setattr("sys.argv", ["run_memory_eval", "--memory-system", "mac"])
    args = run_memory_eval.parse_args()
    assert args.mac_unified_ops_extraction is False
    assert MACMemoryConfig().unified_ops_extraction is False
    assert not hasattr(args, "mac_live_validator")


def test_legacy_validator_commands_are_removed():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["verify-validator", "install-validator", "replay-validator", "validator-state"]:
        assert command not in result.stdout


@pytest.mark.parametrize("module", [
    "validators", "validator_generation", "validator_installation", "validator_dispatch",
])
def test_generated_validator_modules_are_not_importable(module):
    import importlib.util

    assert importlib.util.find_spec(f"memory_as_contracts.{module}") is None
