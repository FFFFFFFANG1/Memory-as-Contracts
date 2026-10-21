from __future__ import annotations

from bench.MAC.agent.memory.mac import (
    BenchMACAdapter,
    MACMemoryConfig,
    _activate_prompt_contracts,
    _blocked_execution,
    _blocked_constraint_items,
    _looks_like_durable_constraint,
    _macbench_active_paths_for_request,
    _macbench_scope_path_for_turn,
    _normalize_history_contract,
    _should_extract_history_turn,
)
from datetime import datetime, timezone

from bench.MAC.agent.memory.base import MemoryRequest
from memory_as_contracts.adapters.base import AdapterContext
from memory_as_contracts.models import (
    Contract,
    ContractKind,
    ContractSource,
    ContractStatus,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleEffect,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
)
from memory_as_contracts.retrieval import _path_matches
from memory_as_contracts.store import ContractStore


def test_bench_history_filter_uses_constraint_metadata() -> None:
    assert _should_extract_history_turn(
        {
            "kind": "introduce",
            "introduce_mode": "constraint_only",
            "mentions_constraint": True,
            "content": "For this project, always return JSON.",
        }
    )
    assert not _should_extract_history_turn(
        {
            "kind": "carryover",
            "mentions_constraint": False,
            "content": "Please use the tools to confirm the release date.",
        }
    )


def test_history_filter_falls_back_to_durable_text_markers() -> None:
    assert _looks_like_durable_constraint(
        "Formatting note: for this project, every answer must end with END."
    )
    assert not _looks_like_durable_constraint(
        "Please use the tools to confirm the release date."
    )


def test_prompt_activation_does_not_deactivate_not_retrieved_contracts() -> None:
    store = ContractStore(":memory:")
    store.init_db()
    store.add_contract(_contract("MAC-keep"))
    store.add_contract(_contract("MAC-drop"))

    activated = _activate_prompt_contracts(
        store,
        "MAC reminders\nGlobal rules:\n- MAC-keep [user_turn;active;session] keep",
    )

    assert activated == {"MAC-keep"}
    assert store.get_contract("MAC-keep").status == ContractStatus.ACTIVE
    assert store.get_contract("MAC-drop").status == ContractStatus.ACTIVE


def test_macbench_project_and_phase_scopes_are_virtual_paths() -> None:
    task = _task_with_grounding()
    turn = {
        "scope": "phase",
        "content": (
            "For the WikiLeaks Disclosure Timeline Project, in the Source Verification Phase, "
            "always cite the retrieval source."
        ),
        "scope_expression": "WikiLeaks Disclosure Timeline Project / Source Verification Phase",
    }

    assert (
        _macbench_scope_path_for_turn(turn, task)
        == "macbench/projects/wikileaks-disclosure-timeline-project/phases/source-verification-phase"
    )

    project_turn = {
        "scope": "project",
        "content": "For the WikiLeaks Disclosure Timeline Project, always use Markdown.",
        "scope_expression": "WikiLeaks Disclosure Timeline Project",
    }
    assert (
        _macbench_scope_path_for_turn(project_turn, task)
        == "macbench/projects/wikileaks-disclosure-timeline-project"
    )


def test_macbench_active_paths_use_project_when_phase_is_unknown() -> None:
    request = MemoryRequest(
        task_uid="task-1",
        agent="bench",
        user_prompt="When did WikiLeaks leak the standard US army protocol at Guantanamo Bay?",
        past_user_turns=[],
        task=_task_with_grounding(),
    )

    assert _macbench_active_paths_for_request(request) == [
        "macbench/projects/wikileaks-disclosure-timeline-project",
    ]


def test_macbench_active_paths_inherit_recent_phase_within_project() -> None:
    request = MemoryRequest(
        task_uid="task-1",
        agent="bench",
        user_prompt="When did WikiLeaks leak the standard US army protocol at Guantanamo Bay?",
        past_user_turns=[
            {
                "scope": "phase",
                "content": "For the WikiLeaks Disclosure Timeline Project, in the Source Verification Phase, cite tools.",
                "scope_expression": "WikiLeaks Disclosure Timeline Project / Source Verification Phase",
            }
        ],
        task=_task_with_grounding(),
    )

    assert _macbench_active_paths_for_request(request) == [
        "macbench/projects/wikileaks-disclosure-timeline-project",
        "macbench/projects/wikileaks-disclosure-timeline-project/phases/source-verification-phase",
    ]


def test_prompt_path_matching_does_not_match_child_scope_from_parent_target() -> None:
    project = "macbench/projects/wikileaks-disclosure-timeline-project"
    phase = f"{project}/phases/source-verification-phase"

    assert _path_matches(phase, project)
    assert not _path_matches(project, phase)


def test_blocked_tool_return_tells_agent_to_revise() -> None:
    execution = _blocked_execution(
        "call-1",
        "search",
        {"query": "x"},
        [{"text": "Use no more than one search call.", "repair": "Do not make another search call."}],
    )

    assert "[memory] This tool call is not allowed due to" in execution.content
    assert "Use no more than one search call." in execution.content
    assert "Please retry after revise" in execution.content
    assert "repair: Do not make another search call." in execution.content
    assert execution.result["memory_rejected"] is True


def test_blocked_constraint_items_only_include_reject_verdicts() -> None:
    store = ContractStore(":memory:")
    store.init_db()
    store.add_contract(_contract("MAC-reject").model_copy(update={"text": "Return JSON."}))
    store.add_contract(_contract("MAC-allow").model_copy(update={"text": "Use tool evidence."}))

    items = _blocked_constraint_items(
        store,
        {
            "contracts_used": ["MAC-reject", "MAC-allow"],
            "validator_verdicts": [
                {
                    "contract_id": "MAC-reject",
                    "decision": "reject",
                    "evidence": {"repair_hint": "Rewrite as JSON."},
                },
                {
                    "contract_id": "MAC-allow",
                    "decision": "allow",
                    "evidence": {},
                },
            ],
        },
    )

    assert items == [{"text": "Return JSON.", "repair": "Rewrite as JSON."}]


def test_bench_adapter_injects_active_paths_into_prompt_and_actions() -> None:
    active_path = "macbench/projects/wikileaks-disclosure-timeline-project"
    adapter = BenchMACAdapter(
        agent="bench",
        tools=[{"name": "send_message", "description": "", "input_schema": {}}],
        token_budget=1000,
        active_paths=[active_path],
    )
    context = AdapterContext(workspace="/workspace", cwd="/workspace", session_id="sess")

    prompt_context = adapter.build_prompt_context("WikiLeaks question", context)
    signature = adapter.build_action_signature(
        {"tool_name": "send_message", "tool_input": {"response": "ok"}},
        context,
    )

    assert active_path in prompt_context.target_paths
    assert active_path in signature.targets


def test_normalize_history_contract_overrides_policy_scope_to_path() -> None:
    contract = _contract("MAC-policy").model_copy(
        update={
            "policy_ir": {
                "text": "For this phase, answer in Markdown.",
                "effect": "require",
                "scope": {"level": "workspace"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {"kind": "response", "predicate": {"field": "response", "op": "exists"}},
            }
        }
    )
    normalized = _normalize_history_contract(
        contract,
        scope_path="macbench/projects/wiki/phases/source",
        workspace="/workspace",
    )

    assert normalized.scope.level == ScopeLevel.PATH
    assert normalized.scope.path == "macbench/projects/wiki/phases/source"
    assert normalized.policy_ir["scope"] == {
        "level": "path",
        "path": "macbench/projects/wiki/phases/source",
    }


def _contract(contract_id: str) -> Contract:
    return Contract(
        id=contract_id,
        text=contract_id,
        effect=RuleEffect.REQUIRE,
        kind=ContractKind.REQUIREMENT,
        modality=Modality.MUST,
        strength=Strength.HARD,
        source=ContractSource(
            kind=SourceKind.USER_TURN,
            created_at=datetime(2026, 7, 4, tzinfo=timezone.utc),
        ),
        scope=Scope(level=ScopeLevel.SESSION),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
    )


def _task_with_grounding() -> dict:
    return {
        "task_chain": {
            "project_phase_grounding": {
                "projects": [
                    {
                        "name": "UN Security Council Resolutions Archive Project",
                        "summary": "Builds a structured archive of UN Security Council resolutions.",
                        "phases": [],
                    },
                    {
                        "name": "WikiLeaks Disclosure Timeline Project",
                        "summary": "Compiles a verified timeline of WikiLeaks disclosures.",
                        "phases": [
                            {
                                "name": "Source Verification Phase",
                                "summary": "Cross-checks disclosure dates.",
                            },
                            {
                                "name": "Executive Briefing Phase",
                                "summary": "Produces briefing materials.",
                            },
                        ],
                    },
                ]
            }
        }
    }
