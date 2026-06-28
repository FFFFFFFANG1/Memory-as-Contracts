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
    ValidatorProvisioner,
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
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.PROJECT, workspace="/workspace/project", project="project"),
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
            created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.PROJECT, workspace="/workspace/project", project="project"),
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


CHECK_ASK_CODE = (
    "def check(action, log, context):\n"
    "    if not action.get('arguments'):\n"
    "        return ask('missing action fields')\n"
    "    return ask('need evidence')"
)


BUDGET_SHARED_STATES = {
    "spent_cents": 0,
    "seen_entry_seqs": [],
    "unknown_spend_entry_seqs": [],
    "last_seen_seq": None,
}


BUDGET_UPDATE_CODE = (
    "def update(entry, log, context):\n"
    "    next_state = log.state_read()\n"
    "    seen = list(next_state.get('seen_entry_seqs') or [])\n"
    "    seq = entry.get('seq')\n"
    "    if seq in seen:\n"
    "        return\n"
    "    if seq is not None:\n"
    "        seen.append(seq)\n"
    "    log.state_write({'seen_entry_seqs': seen})"
)


def verified_package(contract: Contract, package: dict, store: ContractStore):
    result = ValidatorSnippetVerifier().verify(
        contract,
        package,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        committed_examples=[purchase_entry()] if contract.update_patterns else [],
    )
    assert result.accepted, result.errors
    return {
        **package,
        "verification_hash": result.verification_hash,
    }


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
          "status": "success",
          "shared_states": {"spent_cents": 0, "seen_entry_seqs": []},
          "check_code": "def check(action, log, context):\\n    return ask('need evidence')",
          "update_code": "def update(entry, log, context):\\n    return",
          "notes": ["uses bounded search"]
        }
        """

    package = ValidatorSnippetGenerator(response_provider).generate(
        contract,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        tool_capsules=[{"name": "checkout"}, {"name": "purchase"}, {"name": "irrelevant_tool"}],
    )

    prompt = seen["prompt"]
    assert package.status == "success"
    assert package.shared_states["spent_cents"] == 0
    assert "IMMUTABLE RULE" in prompt
    assert "enforcement_shape: check_update" in prompt
    assert "log.read spec" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "log.state_read" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "log.state_write" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "Verdict API" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "ACTION LOG SEARCH API" not in prompt
    assert "VERDICT API" not in prompt
    assert "MATCHED COMMITTED ACTION EXAMPLES" in prompt
    assert "Return one strict JSON object containing the hook code" in prompt
    assert "check_code as a Python source string" in prompt
    assert '"price": "$12.00"' in prompt
    assert "Purchased domain for $12.00" not in prompt
    assert "large prompt must not be included" not in prompt
    assert "large observation must not be included" not in prompt
    assert "irrelevant_tool" not in prompt
    assert "PENDING ACTION EXAMPLES" not in prompt
    assert "Do not hard-code literal values" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "required field" in VALIDATOR_GENERATION_SYSTEM_PROMPT


def test_validator_prompt_falls_back_to_all_capsules_when_no_names_match_patterns() -> None:
    prompt = build_validator_generator_prompt(
        budget_contract(),
        committed_examples=[],
        tool_capsules=[{"name": "webshop_step"}, {"name": "env.step"}],
    )

    assert "webshop_step" in prompt
    assert "env.step" in prompt


def test_validator_generator_prompt_defines_runtime_values_as_dicts() -> None:
    prompt = build_validator_generator_prompt(
        git_push_contract(),
        committed_examples=[pytest_entry()],
        tool_capsules=[{"name": "Bash", "parameters": {"command": "string"}}],
    )

    assert "action is a dict" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "entry is a committed action dict" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "Use action.get(...) and entry.get(...)" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "Do not use getattr" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "RUNTIME VALUE SHAPES" not in prompt
    assert "format" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "Only import math or re" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "idempotent for repeated entries" in VALIDATOR_GENERATION_SYSTEM_PROMPT
    assert "state_write" in VALIDATOR_GENERATION_SYSTEM_PROMPT


def test_validator_verifier_rejects_object_style_access_for_mapping_inputs() -> None:
    contract = git_push_contract()
    package = {
        "status": "success",
        "check_code": (
            "def check(action, log, context):\n"
            "    if getattr(action, 'tool_name', None) != 'Bash':\n"
            "        return allow('not bash')\n"
            "    return ask('need evidence')"
        ),
        "shared_states": {},
    }

    result = ValidatorSnippetVerifier().verify(
        contract,
        package,
        store=make_store(),
        session_id="sess-1",
        task_id="task-1",
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
            "status": "success",
            "check_code": (
                "def check(action, log, context):\n"
                "    command = (action.get('arguments') or {}).get('command')\n"
                "    if not command:\n"
                "        return ask('missing command')\n"
                "    return ask(format(command))"
            ),
            "shared_states": {},
        },
        store=make_store(),
        session_id="sess-1",
        task_id="task-1",
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
          "status": "success",
          "shared_states": {"spent_cents": 0},
          "check_code": "def check(action, log, context):\\n    return ask('need runtime fields')",
          "update_code": "def update(entry, log, context):\\n    return",
          "notes": []
        }
        """

    package = ValidatorSnippetGenerator(response_provider).generate(
        budget_contract(),
        store=store,
        session_id="sess-1",
        task_id="task-1",
        tool_capsules=[{"name": "checkout"}],
    )

    assert package.status == "success"
    assert "PENDING ACTION EXAMPLES" not in seen["prompt"]
    assert "tool capsules" in seen["prompt"]


def test_validator_generator_retries_with_verifier_feedback() -> None:
    store = make_store()
    contract = store.add_contract(git_push_contract())
    store.add_action_log_entry(pytest_entry())
    responses = iter(
        [
            (
                '{"status":"success","check_code":"def check(action, log, context):\\n'
                "    return allow('unsafe')\", \"shared_states\":{}}"
            ),
            (
                '{"status":"success","check_code":"def check(action, log, context):\\n'
                "    if not (action.get('arguments') or {}).get('command'):\\n"
                "        return ask('missing command')\\n"
                "    return ask('verify prior tests')\", \"shared_states\":{}}"
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
        tool_capsules=[{"name": "Bash", "parameters": {"command": "string"}}],
    )

    assert package.status == "success"
    assert len(prompts) == 2
    assert "VERIFIER FEEDBACK" in prompts[1]


def test_validator_generator_allows_three_verifier_guided_attempts() -> None:
    store = make_store()
    contract = store.add_contract(git_push_contract())
    store.add_action_log_entry(pytest_entry())
    unsafe = (
        '{"status":"success","check_code":"def check(action, log, context):\\n'
        "    return allow('unsafe')\", \"shared_states\":{}}"
    )
    safe = (
        '{"status":"success","check_code":"def check(action, log, context):\\n'
        "    command = (action.get('arguments') or {}).get('command')\\n"
        "    if not command:\\n"
        "        return ask('missing command')\\n"
        "    return ask('verify prior tests')\", \"shared_states\":{}}"
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
        tool_capsules=[{"name": "Bash", "parameters": {"command": "string"}}],
    )

    assert package.status == "success"
    assert len(prompts) == 3
    assert all("VERIFIER FEEDBACK" in prompt for prompt in prompts[1:])


@pytest.mark.parametrize(
    ("check_code", "update_code", "error_fragment"),
    [
        (
            "def check(action, state):\n    return allow('ok')",
            BUDGET_UPDATE_CODE,
            "check signature",
        ),
        (
            "cache = []\ndef check(action, log, context):\n    return allow('ok')",
            BUDGET_UPDATE_CODE,
            "mutable global",
        ),
        (
            "def check(action, log, context):\n    return {'decision': 'maybe', 'reason': 'x'}",
            BUDGET_UPDATE_CODE,
            "sandbox",
        ),
        (
            "def check(action, log, context):\n"
            "    log.search({'from': 'actions', 'limit': 1})\n"
            "    return ask('need evidence')",
            BUDGET_UPDATE_CODE,
            "log only exposes",
        ),
        (
            CHECK_ASK_CODE,
            (
                "def update(entry, log, context):\n"
                "    spent = log.state_read('spent_cents') or 0\n"
                "    log.state_write({'spent_cents': spent + 1})"
            ),
            "idempotent",
        ),
    ],
)
def test_validator_verifier_rejects_invalid_or_unsafe_packages(
    check_code: str,
    update_code: str,
    error_fragment: str,
) -> None:
    contract = budget_contract()
    package = {
        "status": "success",
        "check_code": check_code,
        "update_code": update_code,
        "shared_states": BUDGET_SHARED_STATES,
    }

    result = ValidatorSnippetVerifier().verify(
        contract,
        package,
        store=make_store(),
        session_id="sess-1",
        task_id="task-1",
        committed_examples=[purchase_entry()],
    )

    assert result.accepted is False
    assert any(error_fragment in error.lower() for error in result.errors)


def test_validator_installer_activates_only_verified_version_and_supersedes_previous() -> None:
    store = make_store()
    contract = store.add_contract(git_push_contract())
    package = {
        "status": "success",
        "check_code": (
            "def check(action, log, context):\n"
            "    if not action.get('arguments'):\n"
            "        return ask('missing action fields')\n"
            "    return ask('run tests first')"
        ),
        "shared_states": {},
    }
    package = verified_package(contract, package, store)
    installer = ValidatorInstaller()

    first = installer.register(
        contract,
        package,
        store=store,
        session_id="sess-1",
        task_id="task-1",
    )
    second = installer.register(
        contract,
        package,
        store=store,
        session_id="sess-1",
        task_id="task-1",
    )

    assert first.status == "success"
    assert first.validator_version is not None
    assert first.validator_version.snippet_hash
    assert first.validator_version.verification_hash
    assert second.status == "success"
    assert len(store.list_validator_versions(contract.id, status=None)) == 2
    assert store.get_active_validator_version(contract.id).id == second.validator_version.id
    assert store.list_validator_installations(contract.id)[-1].status == "success"


def test_store_rejects_direct_activation_of_unverified_validator() -> None:
    store = make_store()

    with pytest.raises(ValueError, match="verified"):
        store.add_validator_version(
            ValidatorVersion(
                contract_id="MAC-before-push",
                enforcement_shape=ValidatorEnforcementShape.CHECK_ONLY,
                check_patterns=git_push_contract().check_patterns,
                check_code="def check(action, log, context):\n    return allow('ok')",
            )
        )


def test_check_update_installation_requires_post_action_capability() -> None:
    store = make_store()
    contract = store.add_contract(budget_contract())
    class FailGenerator:
        def generate_verified(self, *args, **kwargs):
            raise AssertionError("capability gate should happen before generation")

    result = ValidatorProvisioner(FailGenerator()).provision(
        contract,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        tool_capsules=[{"name": "checkout"}],
        supports_post_action=False,
    )

    assert result.status == "fail"
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

    assert check_only_package.status == "success", check_only_package.model_dump()
    assert check_update_package.status == "success", check_update_package.model_dump()


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
        tool_capsules=[{"name": "checkout"}, {"name": "purchase"}],
    )
    installed = ValidatorInstaller().register(
        contract,
        package,
        store=store,
        session_id="sess-1",
        task_id="task-1",
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
    assert package.status == "success", package.model_dump()
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
        committed_examples=store.list_action_log_entries(),
    )
    assert verification.accepted, verification.errors
    version = _validator_version(
        contract,
        package.check_code or "",
        update_code=package.update_code,
        shared_states=package.shared_states,
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
    check_code: str,
    *,
    update_code: str | None = None,
    shared_states: dict,
) -> ValidatorVersion:
    return ValidatorVersion(
        contract_id=contract.id,
        enforcement_shape=contract.validator_enforcement_shape,
        check_patterns=contract.check_patterns,
        update_patterns=contract.update_patterns,
        state_fields=contract.state_fields,
        shared_states=shared_states,
        check_code=check_code,
        update_code=update_code,
    )
