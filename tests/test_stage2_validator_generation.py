from __future__ import annotations

from datetime import datetime, timezone

import pytest
from openai import APIConnectionError, APITimeoutError

from memory_as_contracts.extractor import LLMCallError, OpenAIChatResponseProvider
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionOutcome,
    ArgPattern,
    Contract,
    ContractKind,
    ContractSource,
    GateDecisionType,
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
    ValidatorVersion,
)
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validator_generation import (
    VALIDATOR_GENERATION_SYSTEM_PROMPT,
    ValidatorSnippetGenerator,
    build_validator_generator_prompt,
    matched_action_examples,
)
from memory_as_contracts.validator_installation import (
    ValidatorInstaller,
    ValidatorSnippetVerifier,
)
from memory_as_contracts.validators import ValidatorRuntime


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def budget_contract() -> Contract:
    return Contract(
        id="MAC-budget",
        text="Total cost must not exceed $90.",
        effect=RuleEffect.DENY,
        kind=ContractKind.PROHIBITION,
        modality=Modality.MUST_NOT,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            span="Total cost must not exceed $90.",
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.TASK, workspace="/workspace/project", task="task-1"),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        validator_enforcement_shape=ValidatorEnforcementShape.CHECK_UPDATE,
        check_patterns=[ToolPattern(tool="checkout"), ToolPattern(tool="purchase")],
        update_patterns=[ToolPattern(tool="checkout"), ToolPattern(tool="purchase")],
        state_fields=["spent_cents", "seen_entry_seqs", "unknown_spend_entry_seqs", "last_seen_seq"],
    )


def purchase_entry() -> ActionLogEntryV1:
    return ActionLogEntryV1(
        adapter_id="codex",
        session_id="sess-1",
        agent_id="codex",
        tool_call_id="call-purchase-1",
        tool_name="purchase",
        host_action="purchase",
        arguments={"item": "domain", "price": "$12.00"},
        result_text="Purchased domain for $12.00",
        outcome=ActionOutcome.SUCCESS,
        timestamp=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
    )


def git_push_contract() -> Contract:
    return Contract(
        id="MAC-before-push",
        text="Before git push, run tests.",
        effect=RuleEffect.REQUIRE,
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            span="Before git push, run tests.",
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.TASK, workspace="/workspace/project", task="task-1"),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        validator_enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
        check_patterns=[
            ToolPattern(tool="Bash", args={"command": ArgPattern(regex=r"^git\s+push(\s|$)")})
        ],
    )


def pytest_entry() -> ActionLogEntryV1:
    return ActionLogEntryV1(
        adapter_id="codex",
        session_id="sess-1",
        agent_id="codex",
        tool_call_id="call-pytest-1",
        tool_name="Bash",
        host_action="exec",
        arguments={"command": "uv run pytest -q"},
        result_text="89 passed",
        outcome=ActionOutcome.SUCCESS,
        timestamp=datetime(2026, 6, 6, 11, tzinfo=timezone.utc),
    )


def test_matched_action_examples_prefers_recent_entries_per_tool() -> None:
    old = purchase_entry().model_copy(
        update={
            "seq": 1,
            "tool_call_id": "old",
            "result_text": "old purchase",
            "timestamp": datetime(2026, 6, 6, 10, tzinfo=timezone.utc),
        }
    )
    recent = purchase_entry().model_copy(
        update={
            "seq": 2,
            "tool_call_id": "recent",
            "result_text": "recent purchase",
            "timestamp": datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
        }
    )

    examples = matched_action_examples(
        [old, recent],
        patterns=[ToolPattern(tool="purchase")],
        session_id="sess-1",
        task_id="task-1",
        limit_per_tool=1,
    )

    assert [entry.tool_call_id for entry in examples] == ["recent"]


def test_validator_generator_prompt_includes_shapes_apis_and_examples() -> None:
    store = make_store()
    contract = budget_contract()
    store.add_action_log_entry(
        purchase_entry().model_copy(
            update={
                "arguments": {
                    "item": "domain",
                    "price": "$12.00",
                    "prompt": "large prompt must not be included",
                    "observation": "large observation must not be included",
                    "metadata": {"debug": "must not be included"},
                }
            }
        )
    )
    seen: dict[str, str] = {}

    def response_provider(prompt: str) -> str:
        seen["prompt"] = prompt
        return """
        {
          "status": "ready",
          "initial_state": {"spent_cents": 0, "seen_entry_seqs": []},
          "snippet": "def update(state, entry, log, context):\\n    return state\\ndef check(action, state, log, context):\\n    return allow('ok')",
          "notes": ["uses bounded search"]
        }
        """

    package = ValidatorSnippetGenerator(response_provider).generate(
        contract,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "checkout",
                "host_action": "purchase",
                "arguments": {"items": [{"name": "hosting", "amount": 85.0}]},
            }
        ],
        tool_capsules=[{"name": "checkout"}, {"name": "purchase"}, {"name": "irrelevant_tool"}],
    )

    prompt = seen["prompt"]
    assert package.status == "ready"
    assert package.initial_state["spent_cents"] == 0
    assert "IMMUTABLE RULE" in prompt
    assert "enforcement_shape: check_update" in prompt
    assert "ACTION LOG SEARCH API" in prompt
    assert "log.search(spec)" in prompt
    assert "VERDICT API" in prompt
    assert "MATCHED COMMITTED ACTION EXAMPLES" in prompt
    assert '"price": "$12.00"' in prompt
    assert "Purchased domain for $12.00" not in prompt
    assert "large prompt must not be included" not in prompt
    assert "large observation must not be included" not in prompt
    assert "irrelevant_tool" not in prompt
    assert "PENDING ACTION EXAMPLES" in prompt
    assert "Do not hard-code literal values" in prompt
    assert "required argument or target is missing" in prompt


def test_validator_prompt_falls_back_to_all_capsules_when_no_names_match_patterns() -> None:
    prompt = build_validator_generator_prompt(
        budget_contract(),
        committed_examples=[],
        pending_examples=[],
        tool_capsules=[{"name": "webshop_step"}, {"name": "env.step"}],
    )

    assert "webshop_step" in prompt
    assert "env.step" in prompt


def test_validator_generator_prompt_defines_runtime_values_as_dicts() -> None:
    prompt = build_validator_generator_prompt(
        git_push_contract(),
        committed_examples=[pytest_entry()],
        pending_examples=[
            {
                "tool_name": "Bash",
                "host_action": "exec",
                "arguments": {"command": "git push origin main"},
            }
        ],
        tool_capsules=[{"name": "Bash", "parameters": {"command": "string"}}],
    )

    assert "action is a dict" in prompt
    assert "entry is a dict" in prompt
    assert "Use action.get(...) and entry.get(...)" in prompt
    assert "Do not use getattr" in prompt
    assert "format" in prompt
    assert "Only import math or re" in prompt
    assert "check must be read-only" in prompt
    assert "return unchanged before applying any state transition" in prompt
    assert "update must return a state dict on every path" in prompt


def test_validator_verifier_rejects_object_style_access_for_mapping_inputs() -> None:
    contract = git_push_contract()
    package = {
        "status": "ready",
        "snippet": (
            "def check(action, state, log, context):\n"
            "    if getattr(action, 'tool_name', None) != 'Bash':\n"
            "        return allow('not bash')\n"
            "    return ask('need evidence')"
        ),
        "initial_state": {},
    }

    result = ValidatorSnippetVerifier().verify(
        contract,
        package,
        store=make_store(),
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

    assert result.accepted is False
    assert any(
        "action is a dict; use action.get" in error
        for error in result.errors
    )


def test_validator_sandbox_supports_documented_format_builtin() -> None:
    contract = git_push_contract()
    result = ValidatorSnippetVerifier().verify(
        contract,
        {
            "status": "ready",
            "snippet": (
                "def check(action, state, log, context):\n"
                "    command = (action.get('arguments') or {}).get('command')\n"
                "    if not command:\n"
                "        return ask('missing command')\n"
                "    return ask(format(command))"
            ),
            "initial_state": {},
        },
        store=make_store(),
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

    assert result.accepted, result.errors


def test_validator_generator_uses_tool_capsules_when_pending_examples_are_missing() -> None:
    store = make_store()
    store.add_action_log_entry(purchase_entry())
    seen: dict[str, str] = {}

    def response_provider(prompt: str) -> str:
        seen["prompt"] = prompt
        return """
        {
          "status": "ready",
          "initial_state": {"spent_cents": 0},
          "snippet": "def update(state, entry, log, context):\\n    return state\\ndef check(action, state, log, context):\\n    return ask('need runtime fields')",
          "notes": []
        }
        """

    package = ValidatorSnippetGenerator(response_provider).generate(
        budget_contract(),
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[],
        tool_capsules=[{"name": "checkout"}],
    )

    assert package.status == "ready"
    assert "No pending action examples were available" in seen["prompt"]
    assert "tool capsules" in seen["prompt"]


def test_validator_generator_retries_with_verifier_feedback() -> None:
    store = make_store()
    contract = store.add_contract(git_push_contract())
    store.add_action_log_entry(pytest_entry())
    responses = iter(
        [
            (
                '{"status":"ready","snippet":"def check(action, state, log, context):\\n'
                "    return allow('unsafe')\", \"initial_state\":{}}"
            ),
            (
                '{"status":"ready","snippet":"def check(action, state, log, context):\\n'
                "    if not (action.get('arguments') or {}).get('command'):\\n"
                "        return ask('missing command')\\n"
                "    return ask('verify prior tests')\", \"initial_state\":{}}"
            ),
        ]
    )
    prompts: list[str] = []

    def provider(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    package = ValidatorSnippetGenerator(provider).generate_verified(
        contract,
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
        tool_capsules=[{"name": "Bash", "parameters": {"command": "string"}}],
    )

    assert package.status == "ready"
    assert len(prompts) == 2
    assert "VERIFIER FEEDBACK" in prompts[1]


def test_validator_generator_allows_three_verifier_guided_attempts() -> None:
    store = make_store()
    contract = store.add_contract(git_push_contract())
    store.add_action_log_entry(pytest_entry())
    unsafe = (
        '{"status":"ready","snippet":"def check(action, state, log, context):\\n'
        "    return allow('unsafe')\", \"initial_state\":{}}"
    )
    safe = (
        '{"status":"ready","snippet":"def check(action, state, log, context):\\n'
        "    command = (action.get('arguments') or {}).get('command')\\n"
        "    if not command:\\n"
        "        return ask('missing command')\\n"
        "    return ask('verify prior tests')\", \"initial_state\":{}}"
    )
    responses = iter([unsafe, unsafe, safe])
    prompts: list[str] = []

    def provider(prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    package = ValidatorSnippetGenerator(provider).generate_verified(
        contract,
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
        tool_capsules=[{"name": "Bash", "parameters": {"command": "string"}}],
    )

    assert package.status == "ready"
    assert len(prompts) == 3
    assert all("VERIFIER FEEDBACK" in prompt for prompt in prompts[1:])


@pytest.mark.parametrize(
    ("snippet", "error_fragment"),
    [
        (
            "def check(action, state):\n    return allow('ok')",
            "check signature",
        ),
        (
            "cache = []\ndef check(action, state, log, context):\n    return allow('ok')",
            "mutable global",
        ),
        (
            (
                "def update(state, entry, log, context):\n"
                "    return state\n"
                "def check(action, state, log, context):\n"
                "    return {'decision': 'maybe', 'reason': 'x'}"
            ),
            "sandbox",
        ),
        (
            (
                "def update(state, entry, log, context):\n"
                "    state['count'] = state.get('count', 0) + 1\n"
                "    return state\n"
                "def check(action, state, log, context):\n"
                "    return ask('need evidence')"
            ),
            "idempotent",
        ),
    ],
)
def test_validator_verifier_rejects_invalid_or_unsafe_packages(
    snippet: str,
    error_fragment: str,
) -> None:
    contract = budget_contract()
    package = {
        "status": "ready",
        "snippet": snippet,
        "initial_state": {field: [] if "seqs" in field else 0 for field in contract.state_fields},
    }

    result = ValidatorSnippetVerifier().verify(
        contract,
        package,
        store=make_store(),
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "checkout",
                "host_action": "purchase",
                "arguments": {"amount": 12},
            }
        ],
        committed_examples=[purchase_entry()],
    )

    assert result.accepted is False
    assert any(error_fragment in error.lower() for error in result.errors)


def test_validator_installer_activates_only_verified_version_and_supersedes_previous() -> None:
    store = make_store()
    contract = store.add_contract(git_push_contract())
    package = {
        "status": "ready",
        "snippet": (
            "def check(action, state, log, context):\n"
            "    if not action.get('arguments'):\n"
            "        return ask('missing action fields')\n"
            "    return ask('run tests first')"
        ),
        "initial_state": {},
    }
    installer = ValidatorInstaller()

    first = installer.install(
        contract,
        package,
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
    second = installer.install(
        contract,
        package,
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

    assert first.status == "installed"
    assert first.validator_version is not None
    assert first.validator_version.snippet_hash
    assert first.validator_version.verification_hash
    assert second.status == "installed"
    assert len(store.list_validator_versions(contract.id, status=None)) == 2
    assert store.get_active_validator_version(contract.id).id == second.validator_version.id
    assert store.list_validator_installations(contract.id)[-1].status == "installed"


def test_store_rejects_direct_activation_of_unverified_validator() -> None:
    store = make_store()

    with pytest.raises(ValueError, match="verified"):
        store.add_validator_version(
            ValidatorVersion(
                contract_id="MAC-before-push",
                enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
                check_patterns=git_push_contract().check_patterns,
                snippet="def check(action, state, log, context):\n    return allow('ok')",
            )
        )


def test_check_update_installation_requires_post_action_capability() -> None:
    store = make_store()
    contract = store.add_contract(budget_contract())
    result = ValidatorInstaller().install(
        contract,
        {
            "status": "ready",
            "snippet": (
                "def update(state, entry, log, context):\n"
                "    return state\n"
                "def check(action, state, log, context):\n"
                "    return ask('need evidence')"
            ),
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
        committed_examples=[purchase_entry()],
        supports_post_action=False,
    )

    assert result.status == "manual_review"
    assert "post-action" in result.errors[0]


@pytest.mark.live_llm
def test_live_llm_validator_generator_produces_runnable_snippets_for_check_shapes() -> None:
    try:
        provider = OpenAIChatResponseProvider.from_env(
            system_prompt=VALIDATOR_GENERATION_SYSTEM_PROMPT
        )
    except ValueError as exc:
        pytest.skip(str(exc))

    try:
        check_only_package = _generate_live_check_only(provider)
        check_update_package = _generate_live_check_update(provider)
    except (APIConnectionError, APITimeoutError, LLMCallError) as exc:
        pytest.skip(f"live LLM endpoint unavailable: {exc}")

    assert check_only_package.status == "ready", check_only_package.model_dump()
    assert check_update_package.status == "ready", check_update_package.model_dump()


def _generate_live_check_only(provider: OpenAIChatResponseProvider):
    store = make_store()
    contract = git_push_contract()
    store.add_contract(contract)
    store.add_action_log_entry(pytest_entry())

    package = ValidatorSnippetGenerator(provider).generate_verified(
        contract,
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
        tool_capsules=[{"name": "Bash", "parameters": {"command": "string"}}],
    )
    _assert_runnable_check(
        store,
        contract,
        package,
        pending_tool="Bash",
        pending_arguments={"command": "git push origin main"},
    )
    return package


def _generate_live_check_update(provider: OpenAIChatResponseProvider):
    store = make_store()
    contract = budget_contract()
    store.add_contract(contract)
    store.add_action_log_entry(purchase_entry())

    package = ValidatorSnippetGenerator(provider).generate_verified(
        contract,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "checkout",
                "host_action": "purchase",
                "arguments": {"items": [{"name": "hosting", "amount": 85.0}]},
            }
        ],
        tool_capsules=[{"name": "checkout"}, {"name": "purchase"}],
    )
    installed = ValidatorInstaller().install(
        contract,
        package,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[
            {
                "tool_name": "checkout",
                "host_action": "purchase",
                "arguments": {"items": [{"name": "hosting", "amount": 85.0}]},
            }
        ],
        committed_examples=[purchase_entry()],
    )
    version = installed.validator_version
    assert version is not None, installed.errors
    ValidatorRuntime(store).record_committed_action(purchase_entry())
    _assert_runnable_check(
        store,
        contract,
        package,
        pending_tool="checkout",
        pending_arguments={"items": [{"name": "hosting", "amount": 85.0}]},
    )
    return package


def _assert_runnable_check(
    store: ContractStore,
    contract: Contract,
    package,
    *,
    pending_tool: str,
    pending_arguments: dict,
) -> None:
    assert package.status == "ready", package.model_dump()
    pending = {
        "tool_name": pending_tool,
        "host_action": pending_tool,
        "arguments": pending_arguments,
    }
    verification = ValidatorSnippetVerifier().verify(
        contract,
        package,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=[pending],
        committed_examples=store.list_action_log_entries(),
    )
    assert verification.accepted, verification.errors
    version = _validator_version(
        contract,
        package.snippet or "",
        initial_state=package.initial_state,
    )
    signature = ActionSignatureBuilder().build(
        tool_name=pending_tool,
        raw_arguments=pending_arguments,
        context=SignatureContext(
            session_id="sess-1",
            task_id="task-1",
            cwd="/workspace/project",
            repo="project",
            now=datetime(2026, 6, 6, 12, tzinfo=timezone.utc),
        ),
    )
    verdict = ValidatorRuntime(store).check(version, signature)
    assert verdict.decision in set(GateDecisionType)


def _validator_version(
    contract: Contract,
    snippet: str,
    *,
    initial_state: dict,
) -> ValidatorVersion:
    return ValidatorVersion(
        contract_id=contract.id,
        enforcement_shape=contract.validator_enforcement_shape,
        check_patterns=contract.check_patterns,
        update_patterns=contract.update_patterns,
        state_fields=contract.state_fields,
        initial_state=initial_state,
        snippet=snippet,
    )
