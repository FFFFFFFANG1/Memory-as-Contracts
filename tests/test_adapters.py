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
from memory_as_contracts.models import (
    ActionConstraints,
    ArgPattern,
    Contract,
    ContractKind,
    ContractSource,
    ContractStatus,
    EdgeRelation,
    Lifecycle,
    LifecycleType,
    Modality,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
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


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


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


def push_prohibition(workspace: Path) -> Contract:
    return Contract(
        id="MAC-push",
        text="Do not push any code changes to Git before asking me.",
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            span="Do not push any code changes to Git before asking me.",
            created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        ),
        scope=Scope(
            level=ScopeLevel.PROJECT,
            workspace=str(workspace.resolve(strict=False)),
            repo="repo",
        ),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        action_constraints=ActionConstraints(
            host_actions=["git.push"],
            canonical_tags=["external_write", "publish_code"],
        ),
        tool_patterns=[
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
                span="Do not push any code changes to Git before asking me.",
                created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
            ),
        }
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
            span="Prefer concise implementation notes.",
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


def test_refresh_changed_sources_skips_unchanged_and_updates_snapshot_after_extraction(
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

    adapter.cold_start_import(store, extractor, ctx)
    assert len(extractor.calls) == 1

    assert adapter.refresh_changed_sources(store, extractor, ctx) == []
    assert len(extractor.calls) == 1

    write(workspace / "AGENTS.md", "Do not push without asking.\nAlways run tests before committing.\n")
    adapter.refresh_changed_sources(store, extractor, ctx)

    assert len(extractor.calls) == 2
    assert "+Always run tests before committing." in extractor.calls[-1]["text"]
    snapshots = store.list_source_snapshots()
    assert len(snapshots) == 1
    assert "Always run tests before committing." in snapshots[0].content


def test_refresh_changed_sources_routes_extracted_contracts_through_resolver(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "repo"
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    write(workspace / "AGENTS.md", "Initial project instructions.\n")
    store = make_store()
    store.add_contract(push_prohibition(workspace).model_copy(update={"id": "MAC-user-push"}))
    adapter = CodexAdapter()
    adapter.cold_start_import(store, RecordingExtractor(), context(workspace))

    write(workspace / "AGENTS.md", "Do not push any code changes to Git before asking me.\n")
    resolved = adapter.refresh_changed_sources(
        store,
        RecordingExtractor([push_prohibition_from_project_doc(workspace)]),
        context(workspace),
    )

    assert resolved[0].status == ContractStatus.REJECTED
    assert store.get_contract("MAC-project-push").status == ContractStatus.REJECTED
    assert store.get_contract("MAC-user-push").status == ContractStatus.ACTIVE
    edges = store.list_edges()
    assert len(edges) == 1
    assert edges[0].relation == EdgeRelation.DUPLICATE


def test_codex_and_claude_hook_payloads_add_prompt_context_and_block(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    store = make_store()
    store.add_contract(push_prohibition(workspace))
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


def test_openclaw_bridge_and_nanobot_function_interface_block_actions(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    ctx = context(workspace)

    openclaw_store = make_store()
    openclaw_store.add_contract(push_prohibition(workspace))
    openclaw_payload = OpenClawAdapter().bridge_before_tool_call(
        openclaw_store,
        {"toolName": "bash", "params": {"command": "git push origin main"}},
        ctx,
    )
    assert openclaw_payload["block"] is True
    assert "Action violates rule MAC-push" in openclaw_payload["reason"]
    assert len(openclaw_store.list_receipts()) == 1

    nanobot_store = make_store()
    nanobot_store.add_contract(push_prohibition(workspace))
    nanobot_payload = gate_nanobot_tool_call(
        nanobot_store,
        {"name": "shell", "arguments": {"command": "git push origin main"}},
        ctx,
    )
    assert nanobot_payload["decision"] == "block"
    assert "Action violates rule MAC-push" in nanobot_payload["reason"]
    assert len(nanobot_store.list_receipts()) == 1
