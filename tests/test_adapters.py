from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from memory_as_contracts.adapters import (
    AdapterContext,
    ClaudeCodeAdapter,
    CodexAdapter,
    NanobotAdapter,
    OpenClawAdapter,
    gate_nanobot_tool_call,
)
from memory_as_contracts.adapters.command import _store_path
from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.extractor import LLMCallError
from memory_as_contracts.models import (
    ArgPattern,
    Contract,
    ContractKind,
    ContractSource,
    ContractStatus,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleEffect,
    RuleSemantics,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
    ValidatorEnforcementShape,
)
from memory_as_contracts.store import ContractStore


class RecordingExtractor:
    def __init__(self, contracts: list[Contract] | None = None) -> None:
        self.calls: list[dict] = []
        self.contracts = contracts or []

    def extract_cold_start_source(
        self,
        *,
        text: str,
        source_kind: SourceKind,
        context,
        path: str | None = None,
        fingerprint: str | None = None,
    ) -> list[Contract]:
        self.calls.append(
            {
                "text": text,
                "source_kind": source_kind,
                "context": context,
                "path": path,
                "fingerprint": fingerprint,
            }
        )
        return list(self.contracts)

    def extract_online_turn(
        self,
        *,
        role: str,
        text: str,
        context,
    ) -> list[Contract]:
        self.calls.append(
            {
                "role": role,
                "text": text,
                "context": context,
            }
        )
        return list(self.contracts)


class TimeoutExtractor:
    def extract_online_turn(self, *, role: str, text: str, context) -> list[Contract]:
        raise LLMCallError.timeout(attempts=3)


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def install_pattern_contract(store: ContractStore, contract: Contract) -> Contract:
    stored = store.add_contract(contract)
    if stored.check_patterns:
        store.install_rule_pattern_version(PolicyCompiler().compile(stored))
    return stored


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def context(workspace: Path, **kwargs) -> AdapterContext:
    return AdapterContext(
        workspace=str(workspace.resolve(strict=False)),
        repo="repo",
        branch="main",
        session_id="sess-1",
        timezone="UTC",
        now=datetime(2026, 5, 25, tzinfo=timezone.utc),
        **kwargs,
    )


def test_adapter_command_store_path_uses_workspace_env_and_cli_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    ctx = context(workspace)
    monkeypatch.chdir(workspace)
    monkeypatch.delenv("MAC_DB_PATH", raising=False)

    assert _store_path(ctx) == workspace.resolve(strict=False) / ".mac" / "contracts.sqlite"

    write(workspace / ".env", "MAC_DB_PATH=.mac/shared.sqlite\n")

    assert _store_path(ctx) == workspace.resolve(strict=False) / ".mac" / "shared.sqlite"
    monkeypatch.delenv("MAC_DB_PATH", raising=False)


def test_hook_snippets_use_uv_run_and_do_not_register_file_diff_refresh() -> None:
    codex = CodexAdapter().hook_config_snippet()
    claude = ClaudeCodeAdapter().hook_config_snippet()

    codex_commands = [
        hook["command"]
        for event in codex["hooks"].values()
        for group in event
        for hook in group["hooks"]
    ]
    claude_commands = [
        hook["command"]
        for event in claude["hooks"].values()
        for group in event
        for hook in group["hooks"]
    ]

    assert codex_commands
    assert claude_commands
    assert all(command.startswith("uv run python -m ") for command in codex_commands)
    assert all(command.startswith("uv run python -m ") for command in claude_commands)
    assert "FileChanged" not in claude["hooks"]


def push_prohibition(workspace: Path) -> Contract:
    return Contract(
        id="MAC-push",
        text="Do not push any code changes to Git before asking me.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        ),
        scope=Scope(
            level=ScopeLevel.PROJECT,
            workspace=str(workspace.resolve(strict=False)),
            project="repo",
        ),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        semantics=RuleSemantics(
            actions=["git.push"],
            tags=["external_write", "publish_code"],
        ),
        check_patterns=[
            ToolPattern(tool="Bash", args={"command": ArgPattern(regex=r"^git\s+push(\s|$)")}),
            ToolPattern(tool="bash", args={"command": ArgPattern(regex=r"^git\s+push(\s|$)")}),
            ToolPattern(tool="shell", args={"command": ArgPattern(regex=r"^git\s+push(\s|$)")}),
        ],
    )


def push_prohibition_from_project_doc(workspace: Path) -> Contract:
    return push_prohibition(workspace).model_copy(
        update={
            "id": "MAC-project-push",
            "source": ContractSource(
                kind=SourceKind.PROJECT_DOC,
                created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
            ),
        }
    )


def before_push_contract(workspace: Path) -> Contract:
    return Contract(
        id="MAC-test-before-push",
        text="Before pushing code, run tests.",
        effect=RuleEffect.REQUIRE,
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        ),
        scope=Scope(
            level=ScopeLevel.PROJECT,
            workspace=str(workspace.resolve(strict=False)),
            project="repo",
        ),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        validator_enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
        check_patterns=[
            ToolPattern(
                tool="exec_command",
                args={"cmd": ArgPattern(regex=r"^git\s+push(\s|$)")},
            )
        ],
    )


def global_preference() -> Contract:
    return Contract(
        id="MAC-pref",
        text="Prefer concise implementation notes.",
        kind=ContractKind.PREFERENCE,
        modality=Modality.SHOULD,
        strength=Strength.SOFT,
        source=ContractSource(
            kind=SourceKind.USER_PROFILE,
            created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.GLOBAL),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
    )


def test_each_adapter_discovers_expected_sources_and_source_kinds(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    write(workspace / "AGENTS.md", "Use uv.")
    write(workspace / "pkg" / "AGENTS.override.md", "Do not push.")
    write(workspace / "CLAUDE.md", "Run tests.")
    write(workspace / ".claude" / "rules" / "security.md", "Never expose secrets.")
    write(workspace / "MEMORY.md", "Always use markdown receipts.")
    write(workspace / "DREAMS.md", "Prefer concise summaries.")
    write(workspace / "memory" / "note.md", "Do not edit generated files.")
    write(workspace / "README.md", "Project docs.")
    write(workspace / "SOUL.md", "You must be careful.")
    write(workspace / "USER.md", "The user prefers direct answers.")
    write(workspace / "memory" / "MEMORY.md", "Do not run npm install.")
    write(workspace / "memory" / "history.jsonl", '{"memory":"Prefer uv."}\n')

    codex_home = tmp_path / "codex_home"
    write(codex_home / "AGENTS.md", "Global codex profile.")
    claude_home = tmp_path / "claude_home"
    write(claude_home / "CLAUDE.md", "Global claude profile.")
    claude_memory = tmp_path / "claude_memory"
    write(claude_memory / "auto.md", "Remember not to push.")

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.setenv("CLAUDE_PROJECT_MEMORY_DIR", str(claude_memory))

    ctx = context(workspace, cwd=str(workspace / "pkg"))

    codex_sources = CodexAdapter().discover_sources(ctx)
    assert {path.name for path in (source.path for source in codex_sources)} == {
        "AGENTS.md",
        "AGENTS.override.md",
    }
    assert {source.source_kind for source in codex_sources} == {
        SourceKind.USER_PROFILE,
        SourceKind.PROJECT_DOC,
    }

    claude_sources = ClaudeCodeAdapter().discover_sources(ctx)
    assert any(source.path.name == "security.md" for source in claude_sources)
    assert any(source.source_kind == SourceKind.MEMORY_FILE for source in claude_sources)
    assert any(source.source_kind == SourceKind.USER_PROFILE for source in claude_sources)

    openclaw_sources = OpenClawAdapter().discover_sources(ctx)
    assert any(source.path.name == "DREAMS.md" for source in openclaw_sources)
    assert any(source.path.name == "README.md" for source in openclaw_sources)
    assert {SourceKind.MEMORY_FILE, SourceKind.PROJECT_DOC}.issubset(
        {source.source_kind for source in openclaw_sources}
    )

    nanobot_sources = NanobotAdapter().discover_sources(ctx)
    assert {source.path.name for source in nanobot_sources} == {
        "SOUL.md",
        "USER.md",
        "MEMORY.md",
        "history.jsonl",
    }
    assert {SourceKind.USER_PROFILE, SourceKind.MEMORY_FILE}.issubset(
        {source.source_kind for source in nanobot_sources}
    )


def test_cold_start_import_calls_extractor_once_per_source_and_snapshots(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    write(workspace / "SOUL.md", "Always ask before deleting files.")
    write(workspace / "USER.md", "Prefer concise summaries.")
    write(workspace / "memory" / "MEMORY.md", "Do not run npm install.")
    write(workspace / "memory" / "history.jsonl", '{"memory":"Use uv."}\n')
    store = make_store()
    extractor = RecordingExtractor()

    NanobotAdapter().cold_start_import(store, extractor, context(workspace))

    assert len(extractor.calls) == 4
    assert len(store.list_source_snapshots()) == 4
    assert {call["source_kind"] for call in extractor.calls} == {
        SourceKind.USER_PROFILE,
        SourceKind.MEMORY_FILE,
    }


def test_adapter_extraction_context_includes_always_on_tool_capsules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write(workspace / "AGENTS.md", "Do not push without asking.\n")
    extractor = RecordingExtractor()

    CodexAdapter().cold_start_import(make_store(), extractor, context(workspace))

    tool_prompt = extractor.calls[0]["context"].tool_capsule_system_prompt
    assert tool_prompt is not None
    assert "Tool definitions available to the acting agent" in tool_prompt
    assert '"name": "exec_command"' in tool_prompt
    assert '"cmd"' in tool_prompt


def test_user_prompt_submit_runs_cold_start_once_before_prompt_retrieval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write(workspace / "AGENTS.md", "Do not push without asking.\n")
    store = make_store()
    adapter = CodexAdapter()
    extractor = RecordingExtractor()
    ctx = context(workspace)

    first = adapter.handle_user_prompt_submit(
        store,
        "first turn",
        ctx,
        extractor_factory=lambda: extractor,
    )
    second = adapter.handle_user_prompt_submit(
        store,
        "second turn",
        ctx,
        extractor_factory=lambda: extractor,
    )

    assert len(extractor.calls) == 1
    assert first.get("hookSpecificOutput", {}) == {}
    assert second.get("hookSpecificOutput", {}) == {}
    snapshots = store.list_source_snapshots()
    assert len(snapshots) == 1
    assert "Do not push without asking." in snapshots[0].content


def test_refresh_changed_sources_is_disabled_for_future_file_diff_work(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write(workspace / "AGENTS.md", "Do not push without asking.\n")
    store = make_store()
    adapter = CodexAdapter()
    extractor = RecordingExtractor([push_prohibition_from_project_doc(workspace)])

    resolved = adapter.refresh_changed_sources(store, extractor, context(workspace))

    assert resolved == []
    assert extractor.calls == []
    assert store.list_source_snapshots() == []


def test_adapter_refines_invalid_patterns_once_before_installing_pattern_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write(workspace / "AGENTS.md", "Do not push code.\n")
    invalid = push_prohibition(workspace).model_copy(
        update={
            "check_patterns": [
                ToolPattern(
                    tool="exec_command",
                    args={"command": ArgPattern(regex="(")},
                )
            ]
        }
    )
    prompts: list[str] = []

    def provider(prompt: str) -> str:
        prompts.append(prompt)
        return (
            '{"check_patterns":[{"tool":"exec_command","args":{"cmd":'
            '{"regex":"^git\\\\s+push(?:\\\\s|$)"}}}],'
            '"update_patterns":[]}'
        )

    store = make_store()
    extracted = CodexAdapter(
        pattern_refiner_factory=lambda: provider,
    ).cold_start_import(
        store,
        RecordingExtractor([invalid]),
        context(workspace),
    )

    assert len(prompts) == 1
    assert extracted[0].status == ContractStatus.ACTIVE
    assert extracted[0].check_patterns[0].tool == "exec_command"
    assert "cmd" in extracted[0].check_patterns[0].args
    assert store.get_active_rule_pattern_version(invalid.id) is not None


def test_codex_and_claude_hook_payloads_add_prompt_context_and_block(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = make_store()
    install_pattern_contract(store, push_prohibition(workspace))
    store.add_contract(global_preference())
    ctx = context(workspace)

    codex = CodexAdapter()
    codex_prompt = codex.handle_user_prompt_submit(store, "Can you push this branch?", ctx)
    assert "additionalContext" in codex_prompt["hookSpecificOutput"]

    codex_gate = codex.gate_event(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
        ctx,
    )
    assert codex_gate["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Action violates rule MAC-push" in codex_gate["hookSpecificOutput"][
        "permissionDecisionReason"
    ]

    claude = ClaudeCodeAdapter()
    claude_prompt = claude.handle_user_prompt_submit(store, "Push branch?", ctx)
    assert "additionalContext" in claude_prompt["hookSpecificOutput"]
    claude_gate = claude.gate_event(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
        ctx,
    )
    assert claude_gate["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert len(store.list_receipts()) == 2


def test_project_scope_uses_workspace_root_when_action_cwd_is_nested(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    nested_cwd = workspace / "packages" / "api"
    nested_cwd.mkdir(parents=True)
    store = make_store()
    install_pattern_contract(store, push_prohibition(workspace))

    result = CodexAdapter().gate_event(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
        context(workspace, cwd=str(nested_cwd)),
    )

    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert store.list_receipts()[-1].contracts_used == ["MAC-push"]


def test_adapter_extracts_and_stores_rules_every_ten_user_turns(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    store = make_store()
    extracted = push_prohibition(workspace).model_copy(update={"id": "MAC-periodic"})
    extractor = RecordingExtractor([extracted])
    adapter = CodexAdapter(online_extractor_factory=lambda: extractor)

    for index in range(1, 10):
        adapter.handle_user_prompt_submit(
            store,
            f"user turn {index}",
            context(workspace, turn_id=f"turn-{index}"),
        )

    assert extractor.calls == []
    assert store.get_contract("MAC-periodic") is None

    adapter.handle_user_prompt_submit(
        store,
        "Do not push this project without asking.",
        context(workspace, turn_id="turn-10"),
    )

    assert len(extractor.calls) == 1
    assert extractor.calls[0]["role"] == "user"
    assert "user turn 1" in extractor.calls[0]["text"]
    assert "Do not push this project without asking." in extractor.calls[0]["text"]
    assert store.get_contract("MAC-periodic") is not None


def test_periodic_extraction_receives_similar_rule_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    store = make_store()
    install_pattern_contract(store, push_prohibition(workspace))
    extractor = RecordingExtractor()
    adapter = CodexAdapter(online_extractor_factory=lambda: extractor)

    for index in range(1, 10):
        adapter.handle_user_prompt_submit(
            store,
            f"noise turn {index}: please continue the current task.",
            context(workspace, turn_id=f"turn-{index}"),
        )
    adapter.handle_user_prompt_submit(
        store,
        (
            "We need to finish this task. [SEP] For this project, never run git push "
            "unless I approve it first."
        ),
        context(workspace, turn_id="turn-10"),
    )

    assert len(extractor.calls) == 1
    similar_context = extractor.calls[0]["context"].similar_rules_system_prompt
    assert similar_context is not None
    assert "Existing similar rules" in similar_context
    assert "Do not push any code changes to Git before asking me." in similar_context


def test_periodic_extraction_filters_similar_rules_by_user_and_session_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    store = make_store()
    cross_workspace = push_prohibition(workspace).model_copy(
        update={
            "id": "MAC-cross-workspace",
            "text": "Do not run git push unless I approve the release.",
            "scope": Scope(
                level=ScopeLevel.PROJECT,
                workspace="/different/workspace",
                project="other-repo",
            ),
        }
    )
    other_user = push_prohibition(workspace).model_copy(
        update={
            "id": "MAC-other-user",
            "text": "Do not run git push for another user's branch.",
            "scope": Scope(
                level=ScopeLevel.GLOBAL,
                user_id="other-user",
            ),
        }
    )
    other_session = push_prohibition(workspace).model_copy(
        update={
            "id": "MAC-other-session",
            "text": "Do not run git push during the old session.",
            "source": push_prohibition(workspace).source.model_copy(
                update={"metadata": {"session_id": "old-session"}}
            ),
        }
    )
    store.add_contract(cross_workspace)
    store.add_contract(other_user)
    store.add_contract(other_session)
    extractor = RecordingExtractor()
    adapter = CodexAdapter(online_extractor_factory=lambda: extractor)

    for index in range(1, 10):
        adapter.handle_user_prompt_submit(
            store,
            f"noise turn {index}: please continue the current task.",
            context(workspace, turn_id=f"turn-{index}", user_id="user-1"),
        )
    adapter.handle_user_prompt_submit(
        store,
        "For this project, never run git push unless I approve it first.",
        context(workspace, turn_id="turn-10", user_id="user-1"),
    )

    similar_context = extractor.calls[0]["context"].similar_rules_system_prompt
    assert similar_context is None


def test_periodic_extraction_limits_similar_rule_context_to_top_five(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    store = make_store()
    for index in range(1, 7):
        store.add_contract(
            push_prohibition(workspace).model_copy(
                update={
                    "id": f"MAC-similar-{index}",
                    "text": f"Do not run git push unless approval rule {index}.",
                }
            )
        )
    extractor = RecordingExtractor()
    adapter = CodexAdapter(online_extractor_factory=lambda: extractor)

    for index in range(1, 10):
        adapter.handle_user_prompt_submit(
            store,
            f"noise turn {index}: please continue the current task.",
            context(workspace, turn_id=f"turn-{index}"),
        )
    adapter.handle_user_prompt_submit(
        store,
        "For this project, never run git push unless I approve it first.",
        context(workspace, turn_id="turn-10"),
    )

    similar_context = extractor.calls[0]["context"].similar_rules_system_prompt
    assert similar_context is not None
    assert similar_context.count("Do not run git push unless approval rule") == 5


def test_periodic_extraction_stores_policy_ir_without_generating_code(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    store = make_store()
    contract = before_push_contract(workspace).model_copy(update={"policy_ir": {
        "text": "Before pushing code, run tests.",
        "effect": "require",
        "scope": {"level": "workspace"},
        "target": {"phase": "pre", "tool": "exec_command", "args": {
            "field": "args.cmd", "op": "regex", "value": r"^git\s+push(\s|$)",
        }},
        "obligation": {"kind": "prior_action", "monitor": {
            "source": "action_log", "where": {
                "field": "tool_name", "op": "eq", "value": "run_tests",
            }, "aggregate": "exists",
        }},
    }})
    extractor = RecordingExtractor([contract])
    adapter = CodexAdapter(online_extractor_factory=lambda: extractor)
    for index in range(1, 11):
        adapter.handle_user_prompt_submit(
            store, f"user turn {index}", context(workspace, turn_id=f"turn-{index}"),
        )
    assert store.get_contract(contract.id).policy_ir == contract.policy_ir
    assert store.list_validator_versions(contract_id=contract.id) == []
    assert store.list_validator_installations(contract.id) == []


def test_periodic_extraction_returns_structured_error_and_keeps_batch_for_retry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    store = make_store()
    adapter = CodexAdapter(online_extractor_factory=TimeoutExtractor)
    result: dict = {}

    for index in range(1, 11):
        result = adapter.handle_user_prompt_submit(
            store,
            f"user turn {index}",
            context(workspace, turn_id=f"turn-{index}"),
        )

    assert result["mac"]["error"] == {
        "code": "llm_timeout",
        "message": "LLM request timed out after 3 attempts",
        "attempts": 3,
    }
    assert len(
        store.pending_user_turns(
            adapter_id="codex",
            session_id="sess-1",
            limit=10,
        )
    ) == 10


def test_openclaw_bridge_and_nanobot_function_interface_block_actions(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    ctx = context(workspace)

    openclaw_store = make_store()
    install_pattern_contract(openclaw_store, push_prohibition(workspace))
    openclaw_payload = OpenClawAdapter().bridge_before_tool_call(
        openclaw_store,
        {"toolName": "bash", "params": {"command": "git push origin main"}},
        ctx,
    )
    assert openclaw_payload["block"] is True
    assert "Action violates rule MAC-push" in openclaw_payload["reason"]
    assert len(openclaw_store.list_receipts()) == 1

    nanobot_store = make_store()
    install_pattern_contract(nanobot_store, push_prohibition(workspace))
    nanobot_payload = gate_nanobot_tool_call(
        nanobot_store,
        {"name": "shell", "arguments": {"command": "git push origin main"}},
        ctx,
    )
    assert nanobot_payload["decision"] == "reject"
    assert "Action violates rule MAC-push" in nanobot_payload["reason"]
    assert len(nanobot_store.list_receipts()) == 1
    assert (workspace / ".mac" / "mac.log").exists()
