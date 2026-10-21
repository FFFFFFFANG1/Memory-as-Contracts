from __future__ import annotations

from datetime import datetime, timezone

from memory_as_contracts.adapters import AdapterContext, CodexAdapter
from memory_as_contracts.models import (
    ArgPattern,
    Contract,
    ContractKind,
    ContractSource,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleEffect,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
    ValidatorEnforcementShape,
)
from memory_as_contracts.store import ContractStore


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def adapter_context(*, turn_id: str | None = "turn-1") -> AdapterContext:
    return AdapterContext(
        workspace="/workspace/project",
        cwd="/workspace/project",
        repo="project",
        session_id="sess-1",
        task_id="task-1",
        turn_id=turn_id,
        now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
    )


def path_contract(path: str = "src/**") -> Contract:
    return Contract(
        id="MAC-path-active",
        text="Check actions while src is the active path.",
        effect=RuleEffect.DENY,
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        ),
        scope=Scope(
            level=ScopeLevel.PATH,
            workspace="/workspace/project",
            path=path,
        ),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        validator_enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
    )


def install_rejecting_policy(
    store: ContractStore,
    contract: Contract,
    *,
    check_patterns: list[ToolPattern],
) -> Contract:
    tools = [pattern.tool for pattern in check_patterns]
    clauses = []
    for pattern in check_patterns:
        terms = [{"field": "tool_name", "op": "eq", "value": pattern.tool}]
        for field, matcher in pattern.args.items():
            if matcher.path_glob is not None:
                terms.append({"field": f"args.{field}", "op": "glob", "value": matcher.path_glob})
        clauses.append({"op": "all", "all": terms})
    return store.add_contract(contract.model_copy(update={"policy_ir": {
        "text": contract.text,
        "effect": "deny",
        "scope": {"level": "path", "path": contract.scope.path},
        "target": {"phase": "pre", "tools": tools, "args": {"op": "any", "any": clauses}},
        "obligation": {"kind": "current_action", "predicate": {
            "field": "tool_name", "op": "in", "value": tools,
        }},
    }}))


def test_path_level_prehook_activates_on_current_tool_path() -> None:
    store = make_store()
    install_rejecting_policy(
        store,
        path_contract(),
        check_patterns=[
            ToolPattern(
                tool="Edit",
                args={"file_path": ArgPattern(path_glob="src/**")},
            )
        ],
    )

    result = CodexAdapter().handle_pre_tool_use(
        store,
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/app.py",
                "old_string": "x",
                "new_string": "y",
            },
        },
        adapter_context(),
    )

    assert result["mac"]["decision"] == "reject"
    assert store.get_hook_turn_state(
        adapter_id="codex",
        session_id="sess-1",
        task_id="task-1",
        turn_id="turn-1",
    )["active_paths"] == ["src/app.py"]


def test_path_level_matching_accumulates_within_user_turn() -> None:
    store = make_store()
    install_rejecting_policy(
        store,
        path_contract(),
        check_patterns=[ToolPattern(tool="Bash")],
    )
    adapter = CodexAdapter()

    first = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Read", "tool_input": {"file_path": "src/app.py"}},
        adapter_context(),
    )
    second = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}},
        adapter_context(),
    )

    assert first["mac"]["decision"] == "allow"
    assert second["mac"]["decision"] == "reject"
    receipts = store.list_receipts()
    assert receipts[-1].targets == ["src/app.py"]


def test_path_scope_matching_is_directional() -> None:
    store = make_store()
    install_rejecting_policy(
        store,
        path_contract("src/sub"),
        check_patterns=[ToolPattern(tool="Bash")],
    )
    adapter = CodexAdapter()

    adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Read", "tool_input": {"file_path": "src"}},
        adapter_context(),
    )
    parent_active = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}},
        adapter_context(),
    )

    assert parent_active["mac"]["decision"] == "allow"

    store = make_store()
    install_rejecting_policy(
        store,
        path_contract("src"),
        check_patterns=[ToolPattern(tool="Bash")],
    )
    adapter = CodexAdapter()
    adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Read", "tool_input": {"file_path": "src/sub/app.py"}},
        adapter_context(),
    )
    child_active = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}},
        adapter_context(),
    )

    assert child_active["mac"]["decision"] == "reject"


def test_posthook_keeps_action_log_as_active_posthook() -> None:
    store = make_store()
    result = CodexAdapter().handle_post_tool_use(
        store,
        {
            "tool_name": "Read",
            "tool_call_id": "call-read",
            "tool_input": {"file_path": "src/app.py"},
            "tool_result": "content",
            "outcome": "success",
        },
        adapter_context(),
    )

    assert result["mac"]["current_active_posthook"] == ["action_log"]
    assert store.list_action_log_entries()[0].targets == ["src/app.py"]
