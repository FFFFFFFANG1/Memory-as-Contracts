from __future__ import annotations

from datetime import datetime, timezone

import pytest

from memory_as_contracts.adapters import AdapterContext, CodexAdapter
from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.gate import ActionGate
from memory_as_contracts.logging_config import configure_logging
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionOutcome,
    ArgPattern,
    AskRequestStatus,
    Contract,
    ContractKind,
    ContractSource,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleEffect,
    RuleValidity,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
    ValidatorEnforcementShape,
    ValidatorVersion,
)
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validator_installation import ValidatorInstaller
from memory_as_contracts.validators import ValidatorRuntime, ValidatorSandboxError


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def install_pattern_contract(store: ContractStore, contract: Contract) -> Contract:
    stored = store.add_contract(contract)
    if stored.tool_patterns:
        store.install_rule_pattern_version(PolicyCompiler().compile(stored))
    return stored


def project_scope() -> Scope:
    return Scope(level=ScopeLevel.PROJECT, workspace="/workspace/project", repo="project")


def source() -> ContractSource:
    return ContractSource(
        kind=SourceKind.USER_TURN,
        span="Before git push, run tests.",
        created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
    )


def git_push_check_contract() -> Contract:
    return Contract(
        id="MAC-test-before-push",
        text="Before git push, run tests.",
        effect=RuleEffect.REQUIRE,
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        strength=Strength.HARD,
        source=source(),
        scope=project_scope(),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        validator_enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
        check_patterns=[
            ToolPattern(tool="Bash", args={"command": ArgPattern(regex=r"^git\s+push(\s|$)")})
        ],
    )


CHECK_ONLY_SNIPPET = """
def update(state, entry, log, context):
    return state

def check(action, state, log, context):
    rows = log.search({
        "from": "actions",
        "select": ["seq"],
        "where": {
            "tool_name": {"in": ["Bash", "exec", "exec_command"]},
            "outcome": {"eq": "success"},
            "any_text": {"regex": r"pytest|uv run pytest"}
        },
        "order_by": [{"field": "seq", "direction": "desc"}],
        "limit": 20
    })
    if rows:
        return allow("Tests passed before git push.", evidence_refs=[{"kind": "action_log_seq", "seq": rows[0]["seq"]}])
    return ask("Run tests before git push.")
"""


def git_push_signature():
    return ActionSignatureBuilder().build(
        tool_name="Bash",
        raw_arguments={"command": "git push origin main"},
        context=SignatureContext(
            session_id="sess-1",
            task_id="task-1",
            cwd="/workspace/project",
            repo="project",
            now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
        ),
    )


def committed_pytest_action() -> ActionLogEntryV1:
    return ActionLogEntryV1(
        adapter_id="codex",
        session_id="sess-1",
        task_id="task-1",
        agent_id="codex",
        tool_call_id="call-test",
        tool_name="Bash",
        host_action="exec",
        arguments={"command": "uv run pytest"},
        result_text="83 passed",
        outcome=ActionOutcome.SUCCESS,
        timestamp=datetime(2026, 6, 6, 11, 55, tzinfo=timezone.utc),
    )


def install_check_only_validator(store: ContractStore) -> None:
    contract = store.add_contract(git_push_check_contract())
    result = ValidatorInstaller().install(
        contract,
        {"status": "ready", "snippet": CHECK_ONLY_SNIPPET, "initial_state": {}},
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "Bash",
                "host_action": "exec",
                "arguments": {"command": "git push origin main"},
            }
        ],
    )
    assert result.status == "installed", result.errors


ASK_BEFORE_PUSH_SNIPPET = """
def check(action, state, log, context):
    return ask("Ask the user before pushing.")
"""


def install_ask_before_push_validator(
    store: ContractStore,
    *,
    check_patterns: list[ToolPattern] | None = None,
) -> ValidatorVersion:
    contract = git_push_check_contract().model_copy(
        update={
            "id": "MAC-ask-before-push",
            "text": "Ask the user before git push.",
            "check_patterns": check_patterns or git_push_check_contract().check_patterns,
        }
    )
    store.add_contract(contract)
    result = ValidatorInstaller().install(
        contract,
        {"status": "ready", "snippet": ASK_BEFORE_PUSH_SNIPPET, "initial_state": {}},
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "Bash",
                "host_action": "exec",
                "arguments": {"command": "git push origin main"},
            }
        ],
    )
    assert result.validator_version is not None, result.errors
    return result.validator_version


def budget_contract() -> Contract:
    return Contract(
        id="MAC-budget",
        text="Total cost must not exceed $90.",
        effect=RuleEffect.DENY,
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=source(),
        scope=project_scope(),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        validator_enforcement_shape=ValidatorEnforcementShape.CHECK_UPDATE,
        check_patterns=[ToolPattern(tool="checkout"), ToolPattern(tool="purchase")],
        update_patterns=[ToolPattern(tool="checkout"), ToolPattern(tool="purchase")],
        state_fields=["spent_cents", "seen_entry_seqs", "unknown_spend_entry_seqs", "last_seen_seq"],
    )


BUDGET_SNIPPET = """
def _amount_cents(payload):
    arguments = payload.get("arguments") or {}
    result = payload.get("result") or {}
    candidates = [
        arguments.get("amount"),
        arguments.get("price"),
        arguments.get("total"),
        result.get("amount") if isinstance(result, dict) else None,
        result.get("price") if isinstance(result, dict) else None,
        result.get("total") if isinstance(result, dict) else None,
    ]
    items = arguments.get("items")
    if items:
        for item in items:
            candidates.append(item.get("amount"))
            candidates.append(item.get("price"))
    for value in candidates:
        if value is None:
            continue
        if isinstance(value, str):
            value = value.replace("$", "").strip()
        return int(float(value) * 100)
    return None

def update(state, entry, log, context):
    state.setdefault("spent_cents", 0)
    state.setdefault("seen_entry_seqs", [])
    state.setdefault("unknown_spend_entry_seqs", [])
    seq = entry["seq"]
    if seq in state["seen_entry_seqs"]:
        return state
    amount = _amount_cents(entry)
    if amount is None:
        state["unknown_spend_entry_seqs"].append(seq)
        return state
    state["spent_cents"] += amount
    state["seen_entry_seqs"].append(seq)
    state["last_seen_seq"] = seq
    return state

def check(action, state, log, context):
    proposed = _amount_cents(action)
    if proposed is None:
        return ask("Cannot determine proposed cost.")
    if state.get("spent_cents", 0) + proposed > 9000:
        return reject("Budget would exceed $90.")
    return allow("Budget remains under $90.")
"""


def install_budget_validator(
    store: ContractStore,
    *,
    contract: Contract | None = None,
    user_id: str | None = None,
) -> ValidatorVersion:
    contract = store.add_contract(contract or budget_contract())
    result = ValidatorInstaller().install(
        contract,
        {
            "status": "ready",
            "snippet": BUDGET_SNIPPET,
            "initial_state": {
                "spent_cents": 0,
                "seen_entry_seqs": [],
                "unknown_spend_entry_seqs": [],
                "last_seen_seq": None,
            },
        },
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "checkout",
                "host_action": "purchase",
                "arguments": {"items": [{"name": "hosting", "amount": 10.0}]},
            }
        ],
        committed_examples=[purchase_entry("verification-purchase", 1.0)],
        user_id=user_id,
    )
    assert result.validator_version is not None, result.errors
    return result.validator_version


def purchase_entry(tool_call_id: str, amount: float) -> ActionLogEntryV1:
    return ActionLogEntryV1(
        adapter_id="codex",
        session_id="sess-1",
        task_id="task-1",
        agent_id="codex",
        tool_call_id=tool_call_id,
        tool_name="purchase",
        host_action="purchase",
        arguments={"amount": amount},
        result_text=f"Purchased for ${amount}",
        outcome=ActionOutcome.SUCCESS,
        timestamp=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
        workspace="/workspace/project",
        repo="project",
    )


def checkout_signature(amount: float):
    return ActionSignatureBuilder().build(
        tool_name="checkout",
        raw_arguments={"items": [{"name": "hosting", "amount": amount}]},
        context=SignatureContext(
            session_id="sess-1",
            task_id="task-1",
            cwd="/workspace/project",
            repo="project",
            now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
        ),
    )


def test_check_only_validator_revises_until_required_prior_action_is_logged() -> None:
    store = make_store()
    install_check_only_validator(store)

    without_test = ActionGate(store).gate(git_push_signature())
    store.add_action_log_entry(committed_pytest_action())
    with_test = ActionGate(store).gate(git_push_signature())

    assert without_test.decision.decision.value == "ask"
    assert "Run tests" in without_test.decision.reason
    assert with_test.decision.decision.value == "allow"
    assert with_test.receipt.validator_verdicts == [
        {
            "contract_id": "MAC-test-before-push",
            "validator_version_id": store.get_active_validator_version("MAC-test-before-push").id,
            "decision": "allow",
            "reason": "Tests passed before git push.",
            "evidence_refs": [{"kind": "action_log_seq", "seq": 1}],
            "confidence": 1.0,
        }
    ]
    assert store.get_validator_state(store.get_active_validator_version("MAC-test-before-push").id) is None


def test_check_update_validator_updates_budget_state_and_blocks_overspend() -> None:
    store = make_store()
    version = install_budget_validator(store)
    runtime = ValidatorRuntime(store)

    runtime.record_committed_action(purchase_entry("call-purchase-1", 12.0))
    runtime.record_committed_action(purchase_entry("call-purchase-1", 12.0))

    state = store.get_validator_state(version.id)
    result = ActionGate(store).gate(checkout_signature(85.0))

    assert state is not None
    assert state.state["spent_cents"] == 1200
    assert state.state["seen_entry_seqs"] == [1]
    assert result.decision.decision.value == "reject"
    assert "Budget would exceed" in result.decision.reason


def test_validator_unknown_evidence_does_not_allow_high_risk_action() -> None:
    store = make_store()
    install_budget_validator(store)

    signature = ActionSignatureBuilder().build(
        tool_name="checkout",
        raw_arguments={"cart_id": "cart-with-unknown-total"},
        context=SignatureContext(
            session_id="sess-1",
            task_id="task-1",
            cwd="/workspace/project",
            repo="project",
            now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
        ),
    )
    result = ActionGate(store).gate(signature)

    assert result.decision.decision.value == "ask"
    assert "Cannot determine" in result.decision.reason


def test_missing_validator_and_multi_rule_aggregation_use_reject_over_ask() -> None:
    store = make_store()
    store.add_contract(git_push_check_contract())

    missing_validator = ActionGate(store).gate(git_push_signature())
    assert missing_validator.decision.decision.value == "ask"

    install_pattern_contract(
        store,
        Contract(
            id="MAC-never-push",
            text="Never push this repository.",
            effect=RuleEffect.DENY,
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            tool_patterns=git_push_check_contract().check_patterns,
        )
    )
    aggregated = ActionGate(store).gate(git_push_signature())

    assert aggregated.decision.decision.value == "reject"
    assert set(aggregated.receipt.contracts_used) == {
        "MAC-test-before-push",
        "MAC-never-push",
    }


def test_ask_response_requires_next_user_input_and_is_single_use() -> None:
    store = make_store()
    install_ask_before_push_validator(store)
    adapter = CodexAdapter()
    event = {
        "tool_name": "Bash",
        "tool_call_id": "call-push",
        "tool_input": {"command": "git push origin main"},
    }

    first = adapter.handle_pre_tool_use(store, event, adapter_context())
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(store, "yes", adapter_context())
    assert store.get_ask_request(ask_id).status == AskRequestStatus.RESPONDED
    allowed_once = adapter.handle_pre_tool_use(store, event, adapter_context())
    asks_again = adapter.handle_pre_tool_use(store, event, adapter_context())

    assert first["mac"]["decision"] == "ask"
    assert first["mac"]["requires_user_input"] is True
    assert allowed_once["mac"]["decision"] == "allow"
    assert store.get_ask_request(ask_id).status == AskRequestStatus.CONSUMED
    assert asks_again["mac"]["decision"] == "ask"


def test_ask_response_is_cancelled_when_next_pending_action_uses_a_different_tool() -> None:
    store = make_store()
    install_ask_before_push_validator(store)
    adapter = CodexAdapter()
    push_event = {
        "tool_name": "Bash",
        "tool_call_id": "call-push",
        "tool_input": {"command": "git push origin main"},
    }

    first = adapter.handle_pre_tool_use(store, push_event, adapter_context())
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(store, "continue", adapter_context())
    adapter.handle_pre_tool_use(
        store,
        {
            "tool_name": "Read",
            "tool_call_id": "call-read",
            "tool_input": {"file_path": "README.md"},
        },
        adapter_context(),
    )
    push_after_other_tool = adapter.handle_pre_tool_use(store, push_event, adapter_context())

    assert store.get_ask_request(ask_id).status == AskRequestStatus.CANCELLED
    assert push_after_other_tool["mac"]["decision"] == "ask"


def adapter_context(
    *,
    turn_id: str | None = None,
    now: datetime | None = None,
    task_id: str | None = "task-1",
) -> AdapterContext:
    return AdapterContext(
        workspace="/workspace/project",
        repo="project",
        session_id="sess-1",
        task_id=task_id,
        turn_id=turn_id,
        now=now or datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
    )


def test_ask_response_only_skips_related_rule_and_other_reject_rule_still_wins() -> None:
    store = make_store()
    install_ask_before_push_validator(store)
    adapter = CodexAdapter()
    event = {
        "tool_name": "Bash",
        "tool_call_id": "call-push",
        "tool_input": {"command": "git push origin main"},
    }

    first = adapter.handle_pre_tool_use(store, event, adapter_context())
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(store, "continue", adapter_context())
    install_pattern_contract(
        store,
        Contract(
            id="MAC-never-push-after-response",
            text="Never push this repository.",
            effect=RuleEffect.DENY,
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            tool_patterns=git_push_check_contract().check_patterns,
        )
    )

    result = adapter.handle_pre_tool_use(store, event, adapter_context())

    assert result["mac"]["decision"] == "reject"
    assert store.get_ask_request(ask_id).status == AskRequestStatus.CONSUMED


def test_ask_response_expires_outside_response_turn() -> None:
    store = make_store()
    install_ask_before_push_validator(store)
    adapter = CodexAdapter()
    event = {
        "tool_name": "Bash",
        "tool_call_id": "call-push",
        "tool_input": {"command": "git push origin main"},
    }

    first = adapter.handle_pre_tool_use(
        store,
        event,
        adapter_context(turn_id="turn-1"),
    )
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(
        store,
        "continue",
        adapter_context(turn_id="turn-2"),
    )
    result = adapter.handle_pre_tool_use(
        store,
        event,
        adapter_context(turn_id="turn-3"),
    )

    assert result["mac"]["decision"] == "ask"
    assert store.get_ask_request(ask_id).status == AskRequestStatus.CANCELLED


def test_ask_response_expires_after_thirty_minutes_without_turn_ids() -> None:
    store = make_store()
    install_ask_before_push_validator(store)
    adapter = CodexAdapter()
    event = {
        "tool_name": "Bash",
        "tool_call_id": "call-push",
        "tool_input": {"command": "git push origin main"},
    }

    first = adapter.handle_pre_tool_use(
        store,
        event,
        adapter_context(now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc)),
    )
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(
        store,
        "continue",
        adapter_context(now=datetime(2026, 6, 6, 12, 1, tzinfo=timezone.utc)),
    )
    result = adapter.handle_pre_tool_use(
        store,
        event,
        adapter_context(now=datetime(2026, 6, 6, 12, 32, tzinfo=timezone.utc)),
    )

    assert result["mac"]["decision"] == "ask"
    assert store.get_ask_request(ask_id).status == AskRequestStatus.CANCELLED


def test_user_input_does_not_respond_to_an_ask_request_from_another_task() -> None:
    store = make_store()
    install_ask_before_push_validator(store)
    adapter = CodexAdapter()
    event = {
        "tool_name": "Bash",
        "tool_call_id": "call-push",
        "tool_input": {"command": "git push origin main"},
    }

    first = adapter.handle_pre_tool_use(
        store,
        event,
        adapter_context(task_id="task-1"),
    )
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(
        store,
        "unrelated task input",
        adapter_context(task_id="task-2"),
    )

    assert store.get_ask_request(ask_id).status == AskRequestStatus.REQUIRED


def test_ask_response_tool_matching_is_exact_by_default() -> None:
    store = make_store()
    install_ask_before_push_validator(
        store,
        check_patterns=[
            ToolPattern(tool="Bash"),
            ToolPattern(tool="bash"),
        ],
    )
    adapter = CodexAdapter()

    first = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "git push"}},
        adapter_context(),
    )
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(store, "continue", adapter_context())
    alias_attempt = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "bash", "tool_input": {"command": "git push"}},
        adapter_context(),
    )

    assert alias_attempt["mac"]["decision"] == "ask"
    assert store.get_ask_request(ask_id).status == AskRequestStatus.CANCELLED


def test_adapter_can_define_an_explicit_ask_response_tool_alias_family() -> None:
    class AliasCodexAdapter(CodexAdapter):
        tool_alias_families = (frozenset({"Bash", "bash"}),)

    store = make_store()
    install_ask_before_push_validator(
        store,
        check_patterns=[
            ToolPattern(tool="Bash"),
            ToolPattern(tool="bash"),
        ],
    )
    adapter = AliasCodexAdapter()

    first = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "Bash", "tool_input": {"command": "git push"}},
        adapter_context(),
    )
    ask_id = first["mac"]["ask_id"]
    adapter.handle_user_prompt_submit(store, "continue", adapter_context())
    alias_attempt = adapter.handle_pre_tool_use(
        store,
        {"tool_name": "bash", "tool_input": {"command": "git push"}},
        adapter_context(),
    )

    assert alias_attempt["mac"]["decision"] == "allow"
    assert store.get_ask_request(ask_id).status == AskRequestStatus.CONSUMED


def test_adapter_post_action_logging_records_only_committed_tool_results() -> None:
    store = make_store()
    version = install_budget_validator(store)
    adapter = CodexAdapter()

    post_result = adapter.handle_post_tool_use(
        store,
        {
            "tool_name": "purchase",
            "tool_call_id": "call-purchase-1",
            "tool_input": {"amount": 12.0},
            "tool_result": {"receipt": "ok"},
            "result_text": "Purchased for $12.00",
            "outcome": "success",
        },
        adapter_context(),
    )

    entries = store.list_action_log_entries()
    state = store.get_validator_state(version.id)
    assert post_result["mac"]["action_log_seq"] == 1
    assert len(entries) == 1
    assert entries[0].tool_name == "purchase"
    assert state is not None
    assert state.state["spent_cents"] == 1200


def test_adapter_pre_action_denial_does_not_create_action_log_entry() -> None:
    store = make_store()
    install_pattern_contract(
        store,
        Contract(
            id="MAC-no-push",
            text="Do not run git push.",
            effect=RuleEffect.DENY,
            kind=ContractKind.PROHIBITION,
            modality=Modality.MUST_NOT,
            strength=Strength.HARD,
            source=source(),
            scope=project_scope(),
            lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
            tool_patterns=[
                ToolPattern(tool="Bash", args={"command": ArgPattern(regex=r"^git\s+push(\s|$)")})
            ],
        )
    )
    adapter = CodexAdapter()

    result = adapter.handle_pre_tool_use(
        store,
        {
            "tool_name": "Bash",
            "tool_call_id": "call-push",
            "tool_input": {"command": "git push origin main"},
        },
        adapter_context(),
    )

    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert store.list_action_log_entries() == []


def test_validator_sandbox_rejects_file_io_snippet() -> None:
    store = make_store()
    contract = store.add_contract(git_push_check_contract())
    version = ValidatorVersion(
        contract_id=contract.id,
        enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
        check_patterns=contract.check_patterns,
        snippet="""
def check(action, state, log, context):
    handle = open("leak.txt", "w")
    handle.write("not allowed")
    return allow("unsafe")
""",
    )

    with pytest.raises(ValidatorSandboxError, match="NameError"):
        ValidatorRuntime(store).check(version, git_push_signature())


def test_validator_sandbox_exposes_rpc_log_proxy_not_full_action_log() -> None:
    store = make_store()
    contract = store.add_contract(git_push_check_contract())
    store.add_action_log_entry(committed_pytest_action())
    version = ValidatorVersion(
        contract_id=contract.id,
        enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
        check_patterns=contract.check_patterns,
        status="rejected",
        snippet="""
def check(action, state, log, context):
    if hasattr(log, "entries"):
        return reject("worker received the full action log")
    rows = log.search({
        "from": "actions",
        "select": ["seq"],
        "where": {"arguments.command": {"regex": "pytest"}},
        "limit": 5
    })
    return allow("rpc search succeeded") if rows else ask("missing evidence")
""",
    )

    verdict = ValidatorRuntime(store).check(version, git_push_signature())

    assert verdict.decision.value == "allow"


def test_validator_sandbox_enforces_search_query_budget() -> None:
    store = make_store()
    contract = store.add_contract(git_push_check_contract())
    version = ValidatorVersion(
        contract_id=contract.id,
        enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
        check_patterns=contract.check_patterns,
        status="rejected",
        snippet="""
def check(action, state, log, context):
    for _ in range(9):
        log.search({"from": "actions", "select": ["seq"], "where": {}, "limit": 1})
    return allow("unreachable")
""",
    )

    with pytest.raises(ValidatorSandboxError, match="query budget"):
        ValidatorRuntime(store).check(version, git_push_signature())


def test_validator_state_rebuild_replays_action_log_deterministically() -> None:
    store = make_store()
    version = install_budget_validator(store)
    runtime = ValidatorRuntime(store)

    runtime.record_committed_action(purchase_entry("call-purchase-1", 12.0))
    runtime.record_committed_action(purchase_entry("call-purchase-2", 25.0))
    original = store.get_validator_state(version.id)

    assert original is not None
    store.delete_validator_state(version.id)
    rebuilt = runtime.rebuild_state(version, original.scope_key)

    assert store.get_validator_state(version.id) is not None
    assert rebuilt.state == original.state
    assert rebuilt.state["spent_cents"] == 3700


def test_project_validator_state_accumulates_across_sessions_but_not_other_repos() -> None:
    store = make_store()
    version = install_budget_validator(store)
    runtime = ValidatorRuntime(store)

    runtime.record_committed_action(purchase_entry("scope-a", 12.0))
    runtime.record_committed_action(
        purchase_entry("scope-b", 25.0).model_copy(
            update={"session_id": "sess-2", "task_id": "task-2"}
        )
    )
    runtime.record_committed_action(
        purchase_entry("scope-c", 30.0).model_copy(
            update={"repo": "other", "workspace": "/workspace/other"}
        )
    )

    states = store.list_validator_states(version.id)
    assert [state.state["spent_cents"] for state in states] == [3700]
    assert states[0].revision == 2


def test_global_validator_state_accumulates_by_user_across_sessions() -> None:
    store = make_store()
    contract = budget_contract().model_copy(
        update={
            "id": "MAC-global-budget",
            "scope": Scope(level=ScopeLevel.GLOBAL),
        }
    )
    version = install_budget_validator(store, contract=contract, user_id="user-1")
    runtime = ValidatorRuntime(store)

    runtime.record_committed_action(
        purchase_entry("global-a", 12.0).model_copy(update={"user_id": "user-1"})
    )
    runtime.record_committed_action(
        purchase_entry("global-b", 25.0).model_copy(
            update={"session_id": "sess-2", "task_id": "task-2", "user_id": "user-1"}
        )
    )
    runtime.record_committed_action(
        purchase_entry("global-c", 30.0).model_copy(
            update={"session_id": "sess-3", "task_id": "task-3", "user_id": "user-2"}
        )
    )

    states = store.list_validator_states(version.id)
    assert sorted(state.state["spent_cents"] for state in states) == [3000, 3700]


def test_session_validator_state_accumulates_across_tasks_but_not_sessions() -> None:
    store = make_store()
    contract = budget_contract().model_copy(
        update={
            "id": "MAC-session-budget",
            "scope": Scope(level=ScopeLevel.SESSION),
        }
    )
    version = install_budget_validator(store, contract=contract)
    runtime = ValidatorRuntime(store)

    runtime.record_committed_action(purchase_entry("session-a", 12.0))
    runtime.record_committed_action(
        purchase_entry("session-b", 25.0).model_copy(update={"task_id": "task-2"})
    )
    runtime.record_committed_action(
        purchase_entry("session-c", 30.0).model_copy(
            update={"session_id": "sess-2", "task_id": "task-3"}
        )
    )

    states = store.list_validator_states(version.id)
    assert sorted(state.state["spent_cents"] for state in states) == [3000, 3700]


def test_action_log_idempotency_key_rejects_conflicting_payload() -> None:
    store = make_store()
    runtime = ValidatorRuntime(store)
    runtime.record_committed_action(purchase_entry("same-call", 12.0))

    with pytest.raises(ValueError, match="idempotency"):
        runtime.record_committed_action(purchase_entry("same-call", 25.0))


def test_post_action_dispatch_skips_expired_or_out_of_scope_contract() -> None:
    store = make_store()
    contract = budget_contract().model_copy(
        update={
            "validity": RuleValidity(
                **{
                    "from": "2026-06-01T00:00:00Z",
                    "until": "2026-06-05T00:00:00Z",
                }
            )
        }
    )
    store.add_contract(contract)
    install_result = ValidatorInstaller().install(
        contract,
        {
            "status": "ready",
            "snippet": BUDGET_SNIPPET,
            "initial_state": {
                "spent_cents": 0,
                "seen_entry_seqs": [],
                "unknown_spend_entry_seqs": [],
                "last_seen_seq": None,
            },
        },
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "checkout",
                "host_action": "purchase",
                "arguments": {"amount": 10.0},
            }
        ],
        committed_examples=[purchase_entry("verify-expired", 1.0)],
    )
    version = install_result.validator_version
    assert version is not None

    ValidatorRuntime(store).record_committed_action(purchase_entry("expired-action", 12.0))

    states = store.list_validator_states(version.id)
    assert len(states) == 1
    assert states[0].state["spent_cents"] == 0
    assert states[0].revision == 0


def test_post_action_runtime_failure_keeps_log_and_marks_state_degraded(tmp_path) -> None:
    log_path = tmp_path / "mac.log"
    configure_logging(path=log_path)
    store = make_store()
    contract = store.add_contract(budget_contract())
    snippet = """
def update(state, entry, log, context):
    state.setdefault("spent_cents", 0)
    state.setdefault("seen_entry_seqs", [])
    state.setdefault("unknown_spend_entry_seqs", [])
    amount = (entry.get("arguments") or {}).get("amount")
    if amount == 13:
        raise ValueError("synthetic runtime failure")
    if entry["seq"] not in state["seen_entry_seqs"]:
        state["spent_cents"] += int(float(amount) * 100)
        state["seen_entry_seqs"].append(entry["seq"])
    return state

def check(action, state, log, context):
    if not action.get("arguments"):
        return ask("missing action fields")
    return allow("ok")
"""
    installed = ValidatorInstaller().install(
        contract,
        {
            "status": "ready",
            "snippet": snippet,
            "initial_state": {
                "spent_cents": 0,
                "seen_entry_seqs": [],
                "unknown_spend_entry_seqs": [],
                "last_seen_seq": None,
            },
        },
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[{"tool_name": "checkout", "arguments": {"amount": 1}}],
        committed_examples=[purchase_entry("verify-runtime-failure", 1.0)],
    )
    version = installed.validator_version
    assert version is not None

    ValidatorRuntime(store).record_committed_action(purchase_entry("runtime-failure", 13.0))

    assert len(store.list_action_log_entries()) == 1
    state = store.get_validator_state(version.id)
    assert state is not None
    assert state.degraded is True
    errors = store.list_validator_runtime_errors(version.id)
    assert len(errors) == 1
    assert errors[0].replay_required is True
    assert "validator.state_degraded" in log_path.read_text(encoding="utf-8")
