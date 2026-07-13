from __future__ import annotations

from datetime import datetime, timezone

from memory_as_contracts.gate import ActionGate
from memory_as_contracts.hook_plan import build_active_hook_plan
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionOutcome,
    AvailableAction,
    Contract,
    ContractSource,
    Lifecycle,
    LifecycleType,
    Modality,
    RuleEffect,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
)
from memory_as_contracts.store import ContractStore
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext
from memory_as_contracts.extractor import ExtractionContext, PolicyIRContractExtractor
from memory_as_contracts.normalizers import NormalizationContext
from memory_as_contracts.retrieval import PromptIntakeRetriever, PromptRetrievalContext
from memory_as_contracts.tool_capsules import ToolCapabilityCapsule, render_tool_capsule_system_prompt


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def source() -> ContractSource:
    return ContractSource(kind=SourceKind.USER_TURN, created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))


def contract(policy_ir: dict, *, contract_id: str = "MAC-policy") -> Contract:
    effect = RuleEffect(policy_ir["effect"])
    modality = Modality.MUST_NOT if effect == RuleEffect.DENY else Modality.MUST
    return Contract(
        id=contract_id,
        text=policy_ir["text"],
        effect=effect,
        kind="prohibition" if effect == RuleEffect.DENY else "requirement",
        modality=modality,
        strength=Strength.HARD,
        source=source(),
        scope=Scope(level=ScopeLevel.SESSION),
        lifecycle=Lifecycle(type=LifecycleType.UNTIL_REVOKED, until_revoked=True),
        policy_ir=policy_ir,
    )


def signature(tool_name: str, arguments: dict, *, available_actions: list[AvailableAction] | None = None):
    return ActionSignatureBuilder().build(
        tool_name=tool_name,
        raw_arguments=arguments,
        context=SignatureContext(
            host="mac-bench",
            agent_family="bench",
            session_id="sess",
            task_id="task",
            workspace="/workspace",
            cwd="/workspace",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
            available_actions=available_actions or [],
        ),
    )


def log_entry(
    tool_name: str,
    *,
    call_id: str,
    turn_id: str | None = None,
    outcome: ActionOutcome = ActionOutcome.SUCCESS,
) -> ActionLogEntryV1:
    return ActionLogEntryV1(
        adapter_id="mac-bench",
        session_id="sess",
        agent_id="bench",
        tool_call_id=call_id,
        tool_name=tool_name,
        host_action=tool_name,
        arguments={},
        result_text="ok",
        outcome=outcome,
        turn_id=turn_id,
    )


def test_policy_ir_rejects_bad_final_response_without_validator() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "The final answer must be JSON with a successor key.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "response",
                    "predicate": {
                        "field": "response",
                        "op": "json_object",
                        "value": {"required_keys": ["successor"]},
                    },
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": "Sabah Al-Khalid"}))

    assert result.decision.decision.value == "reject"
    assert result.receipt.validator_verdicts[0]["policy_ir"] is True
    assert "repair_hint" in result.receipt.validator_verdicts[0]["evidence"]


def test_policy_ir_response_missing_monitor_is_diagnostic_not_reject() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "Before final answer, use the relevant lookup tool.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {"kind": "required_tool_usage", "value": 1},
            },
            contract_id="MAC-ambiguous-response",
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": "done"}))

    assert result.decision.decision.value == "allow"
    verdict = result.receipt.validator_verdicts[0]
    assert verdict["evidence"]["ambiguous"] is True
    assert verdict["confidence"] == 0.0


def test_prompt_retrieval_renders_response_stage_final_checklist() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "The final answer must be JSON with a successor key.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "response",
                    "predicate": {
                        "field": "response",
                        "op": "json_object",
                        "value": {"required_keys": ["successor"]},
                    },
                },
            },
            contract_id="MAC-final-json",
        )
    )

    retriever = PromptIntakeRetriever(store)
    packets = retriever.retrieve(PromptRetrievalContext(session_id="sess", user_turn="Answer the question."))
    rendered = retriever.render_prompt_text(packets)

    assert packets[0].channel == "final-checklist"
    assert "Before final response:" in rendered
    assert "MAC-final-json" in rendered
    assert "final response is JSON with keys successor" in rendered


def test_policy_ir_self_lock_same_tool_is_demoted_from_pre_hook() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "Before sales_estimator, call sales_estimator.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "pre", "tool": "sales_estimator"},
                "obligation": {
                    "kind": "prior_action",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "tool_name", "op": "eq", "value": "sales_estimator"},
                        "aggregate": "count",
                    },
                    "op": "gte",
                    "value": 1,
                },
            },
            contract_id="MAC-self-lock",
        )
    )

    result = ActionGate(store).gate(signature("sales_estimator", {"title": "Portal"}))
    plan = build_active_hook_plan(store, signature("sales_estimator", {"title": "Portal"}), active_paths=[])
    response_result = ActionGate(store).gate(signature("send_message", {"response": "done"}))

    assert result.decision.decision.value == "allow"
    assert not plan.prehook_contracts
    assert response_result.decision.decision.value == "reject"
    assert response_result.receipt.validator_verdicts[0]["evidence"]["kind"] == "prior_action"


def test_policy_ir_generic_tool_call_prior_action_is_demoted() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "Use a tool before using tools.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "pre", "action_family": "tool.call"},
                "obligation": {
                    "kind": "sequence",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "action_family", "op": "eq", "value": "tool.call"},
                        "aggregate": "count",
                    },
                    "op": "gte",
                    "value": 1,
                },
            },
            contract_id="MAC-generic-self-lock",
        )
    )

    result = ActionGate(store).gate(signature("lookup_tool", {"query": "x"}))
    plan = build_active_hook_plan(store, signature("lookup_tool", {"query": "x"}), active_paths=[])

    assert result.decision.decision.value == "allow"
    assert not plan.prehook_contracts


def test_policy_ir_distinct_prior_action_keeps_safe_pre_hook() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "Before release-date lookup, run sales_estimator.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "pre", "tool": "release_date_checker"},
                "obligation": {
                    "kind": "prior_action",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "tool_name", "op": "eq", "value": "sales_estimator"},
                        "aggregate": "count",
                    },
                    "op": "gte",
                    "value": 1,
                },
            },
            contract_id="MAC-safe-prior",
        )
    )

    missing = ActionGate(store).gate(signature("release_date_checker", {"title": "Portal"}))
    store.add_action_log_entry(log_entry("sales_estimator", call_id="sales-1"))
    satisfied = ActionGate(store).gate(signature("release_date_checker", {"title": "Portal"}))

    assert missing.decision.decision.value == "reject"
    assert satisfied.decision.decision.value == "allow"


def test_policy_ir_forbidden_tool_upper_bound_still_rejects_pre_hook() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "Never call web_search.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "pre", "tool": "web_search"},
                "obligation": {
                    "kind": "specific_tool_count",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "tool_name", "op": "eq", "value": "web_search"},
                        "aggregate": "count",
                    },
                    "op": "lte",
                    "value": 0,
                },
            },
            contract_id="MAC-no-web",
        )
    )

    result = ActionGate(store).gate(signature("web_search", {"query": "x"}))
    plan = build_active_hook_plan(store, signature("web_search", {"query": "x"}), active_paths=[])

    assert result.decision.decision.value == "reject"
    assert [contract.id for contract in plan.prehook_contracts] == ["MAC-no-web"]


def test_policy_ir_forbidden_current_action_rejects_only_matching_tool() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "Never call web_search.",
                "effect": "deny",
                "scope": {"level": "session"},
                "target": {"phase": "pre", "tool": "web_search"},
                "obligation": {
                    "kind": "current_action",
                    "predicate": {"field": "tool_name", "op": "eq", "value": "web_search"},
                },
            },
            contract_id="MAC-deny-web",
        )
    )

    denied = ActionGate(store).gate(signature("web_search", {"query": "x"}))
    unrelated = ActionGate(store).gate(signature("lookup_tool", {"query": "x"}))
    plan = build_active_hook_plan(store, signature("web_search", {"query": "x"}), active_paths=[])

    assert denied.decision.decision.value == "reject"
    assert unrelated.decision.decision.value == "allow"
    assert [contract.id for contract in plan.prehook_contracts] == ["MAC-deny-web"]


def test_policy_ir_response_char_count_between() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "The final response must be between 10 and 20 characters.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "response",
                    "predicate": {"field": "response", "op": "char_count_between", "value": [10, 20]},
                },
            }
        )
    )

    assert ActionGate(store).gate(signature("send_message", {"response": "1234567890"})).decision.decision.value == "allow"
    assert ActionGate(store).gate(signature("send_message", {"response": "short"})).decision.decision.value == "reject"


def test_policy_ir_same_step_requires_distinct_tools_in_one_turn() -> None:
    store = make_store()
    store.add_action_log_entry(log_entry("city_feature_identifier", call_id="call-1", turn_id="step-1"))
    store.add_action_log_entry(log_entry("city_reputation_identifier", call_id="call-2", turn_id="step-1"))
    store.add_contract(
        contract(
            {
                "text": "Call both city tools in one action step.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "same_step",
                    "monitor": {
                        "source": "action_log",
                        "where": {
                            "field": "tool_name",
                            "op": "in",
                            "value": ["city_feature_identifier", "city_reputation_identifier"],
                        },
                        "aggregate": "distinct_count",
                        "distinct_by": "tool_name",
                        "group_by": "turn_id",
                    },
                    "op": "gte",
                    "value": 2,
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": "done"}))

    assert result.decision.decision.value == "allow"


def test_policy_ir_same_step_rejects_tools_split_across_turns() -> None:
    store = make_store()
    store.add_action_log_entry(log_entry("city_feature_identifier", call_id="call-1", turn_id="step-1"))
    store.add_action_log_entry(log_entry("city_reputation_identifier", call_id="call-2", turn_id="step-2"))
    store.add_contract(
        contract(
            {
                "text": "Call both city tools in one action step.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "same_step",
                    "monitor": {
                        "source": "action_log",
                        "where": {
                            "field": "tool_name",
                            "op": "in",
                            "value": ["city_feature_identifier", "city_reputation_identifier"],
                        },
                        "aggregate": "distinct_count",
                        "distinct_by": "tool_name",
                        "group_by": "turn_id",
                    },
                    "op": "gte",
                    "value": 2,
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": "done"}))

    assert result.decision.decision.value == "reject"


def test_policy_ir_same_step_counts_multiple_calls_to_same_tool() -> None:
    store = make_store()
    store.add_action_log_entry(log_entry("altitude_tool", call_id="call-1", turn_id="step-1"))
    store.add_action_log_entry(log_entry("altitude_tool", call_id="call-2", turn_id="step-1"))
    store.add_contract(
        contract(
            {
                "text": "Call altitude_tool twice in one action step.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "same_step",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "tool_name", "op": "eq", "value": "altitude_tool"},
                        "aggregate": "count",
                        "group_by": "turn_id",
                    },
                    "op": "gte",
                    "value": 2,
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": "done"}))

    assert result.decision.decision.value == "allow"


def test_policy_ir_same_step_range_rejects_group_that_is_too_large() -> None:
    store = make_store()
    store.add_action_log_entry(log_entry("tool_a", call_id="call-1", turn_id="step-1"))
    store.add_action_log_entry(log_entry("tool_b", call_id="call-2", turn_id="step-1"))
    store.add_action_log_entry(log_entry("tool_c", call_id="call-3", turn_id="step-1"))
    store.add_contract(
        contract(
            {
                "text": "Use between 1 and 2 unique tools in one step.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "same_step",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "tool_name", "op": "regex", "value": "tool_.*"},
                        "aggregate": "distinct_count",
                        "distinct_by": "tool_name",
                        "group_by": "turn_id",
                    },
                    "op": "between",
                    "value": [1, 2],
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": "done"}))

    assert result.decision.decision.value == "reject"


def test_policy_ir_allows_satisfied_specific_tool_count() -> None:
    store = make_store()
    store.add_action_log_entry(
        ActionLogEntryV1(
            adapter_id="mac-bench",
            session_id="sess",
            agent_id="bench",
            tool_call_id="call-1",
            tool_name="political_successor_finder",
            host_action="political_successor_finder",
            arguments={},
            result_text="ok",
            outcome=ActionOutcome.SUCCESS,
        )
    )
    store.add_contract(
        contract(
            {
                "text": "Call political_successor_finder at most once.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"tool": "send_message", "phase": "response"},
                "obligation": {
                    "kind": "specific_tool_count",
                    "monitor": {
                        "source": "action_log",
                        "where": {
                            "field": "tool_name",
                            "op": "eq",
                            "value": "political_successor_finder",
                        },
                        "aggregate": "count",
                    },
                    "op": "lte",
                    "value": 1,
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": '{"successor":"x"}'}))

    assert result.decision.decision.value == "allow"
    assert result.receipt.validator_verdicts[0]["policy_ir"] is True


def test_policy_ir_rejects_specific_tool_count_violation() -> None:
    store = make_store()
    for index in range(2):
        store.add_action_log_entry(
            ActionLogEntryV1(
                adapter_id="mac-bench",
                session_id="sess",
                agent_id="bench",
                tool_call_id=f"call-{index}",
                tool_name="political_successor_finder",
                host_action="political_successor_finder",
                arguments={},
                result_text="ok",
                outcome=ActionOutcome.SUCCESS,
            )
        )
    store.add_contract(
        contract(
            {
                "text": "Call political_successor_finder at most once.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"tool": "send_message", "phase": "response"},
                "obligation": {
                    "kind": "specific_tool_count",
                    "monitor": {
                        "source": "action_log",
                        "where": {
                            "field": "tool_name",
                            "op": "eq",
                            "value": "political_successor_finder",
                        },
                        "aggregate": "count",
                    },
                    "op": "lte",
                    "value": 1,
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("send_message", {"response": '{"successor":"x"}'}))

    assert result.decision.decision.value == "reject"


def test_policy_ir_counts_pending_tool_call_for_pre_hook_limit() -> None:
    store = make_store()
    store.add_action_log_entry(
        ActionLogEntryV1(
            adapter_id="mac-bench",
            session_id="sess",
            agent_id="bench",
            tool_call_id="call-1",
            tool_name="political_successor_finder",
            host_action="political_successor_finder",
            arguments={},
            result_text="ok",
            outcome=ActionOutcome.SUCCESS,
        )
    )
    store.add_contract(
        contract(
            {
                "text": "Call political_successor_finder at most once.",
                "effect": "deny",
                "scope": {"level": "session"},
                "target": {"tool": "political_successor_finder", "phase": "pre"},
                "obligation": {
                    "kind": "specific_tool_count",
                    "monitor": {
                        "source": "action_log",
                        "where": {
                            "field": "tool_name",
                            "op": "eq",
                            "value": "political_successor_finder",
                        },
                        "aggregate": "count",
                    },
                    "op": "lte",
                    "value": 1,
                },
            }
        )
    )

    result = ActionGate(store).gate(signature("political_successor_finder", {}))

    assert result.decision.decision.value == "reject"


def test_policy_ir_generic_tool_call_family_matches_registered_external_tool() -> None:
    store = make_store()
    for index in range(3):
        store.add_action_log_entry(
            ActionLogEntryV1(
                adapter_id="mac-bench",
                session_id="sess",
                agent_id="bench",
                tool_call_id=f"call-{index}",
                tool_name=f"lookup_{index}",
                host_action=f"lookup_{index}",
                arguments={},
                result_text="ok",
                outcome=ActionOutcome.SUCCESS,
            )
        )
    store.add_contract(
        contract(
            {
                "text": "Use at most three external tools before answering.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "pre", "action_family": "tool.call"},
                "obligation": {
                    "kind": "tool_count",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "action_family", "op": "eq", "value": "tool.call"},
                        "aggregate": "count",
                    },
                    "op": "lte",
                    "value": 3,
                },
            }
        )
    )

    result = ActionGate(store).gate(
        signature(
            "new_lookup",
            {},
            available_actions=[AvailableAction(name="new_lookup")],
        )
    )

    assert result.decision.decision.value == "reject"


def test_active_hook_plan_filters_policy_ir_by_structured_target() -> None:
    store = make_store()
    store.add_contract(
        contract(
            {
                "text": "Final answer must be JSON.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "response", "action_family": "message.send"},
                "obligation": {
                    "kind": "response",
                    "predicate": {"field": "response", "op": "json_object", "value": {}},
                },
            },
            contract_id="MAC-response",
        )
    )
    store.add_contract(
        contract(
            {
                "text": "Use lookup_tool at most once.",
                "effect": "require",
                "scope": {"level": "session"},
                "target": {"phase": "pre", "tool": "lookup_tool"},
                "obligation": {
                    "kind": "specific_tool_count",
                    "monitor": {
                        "source": "action_log",
                        "where": {"field": "tool_name", "op": "eq", "value": "lookup_tool"},
                        "aggregate": "count",
                    },
                    "op": "lte",
                    "value": 1,
                },
            },
            contract_id="MAC-tool",
        )
    )

    plan = build_active_hook_plan(
        store,
        signature("lookup_tool", {}, available_actions=[AvailableAction(name="lookup_tool")]),
        active_paths=[],
    )

    assert [contract.id for contract in plan.prehook_contracts] == ["MAC-tool"]
    assert [entry.contract_id for entry in plan.current_active_prehook] == ["MAC-tool"]


def test_policy_ir_extractor_accepts_minimal_llm_output() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        assert system_prompt is not None
        return """
        {"policies":[{
          "text":"Return valid JSON with a successor key.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"response",
            "predicate":{"field":"response","op":"json_object","value":{"required_keys":["successor"]}}
          }
        }]}
        """

    context = ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace",
            timezone="UTC",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        session_id="sess",
    )

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Return valid JSON with a successor key.",
        context=context,
    )

    assert len(contracts) == 1
    assert contracts[0].policy_ir is not None
    assert contracts[0].check_patterns == []


def test_policy_ir_extractor_normalizes_response_predicate_target() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Final response must contain follow-up questions.",
          "effect":"require",
          "scope":{"level":"workspace"},
          "target":{"phase":"pre","action_family":"tool.call"},
          "obligation":{
            "kind":"current_action",
            "predicate":{"field":"response","op":"contains","value":"follow-up questions"}
          }
        }]}
        """

    context = ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace",
            timezone="UTC",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        session_id="sess",
    )

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Final response must contain follow-up questions.",
        context=context,
    )

    policy = contracts[0].policy_ir
    assert policy["target"]["phase"] == "response"
    assert policy["target"]["action_family"] == "message.send"
    assert policy["target"]["tools"] == []
    assert policy["obligation"]["kind"] == "response"


def test_policy_ir_extractor_drops_non_executable_current_action_context() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"for the WikiLeaks Disclosure Timeline Project, we're now in the Initial Scoping Phase",
          "effect":"allow",
          "scope":{"level":"path","path":"macbench/projects/wiki/phases/initial"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{"kind":"current_action"}
        }]}
        """

    context = ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace",
            timezone="UTC",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        session_id="sess",
    )
    extractor = PolicyIRContractExtractor(provider)

    contracts = extractor.extract_online_turn(
        role="user",
        text="for the WikiLeaks Disclosure Timeline Project, we're now in the Initial Scoping Phase",
        context=context,
    )

    assert contracts == []
    assert extractor.drain_diagnostics()[0]["unsupported_count"] == 1


def test_policy_ir_extractor_drops_response_policy_without_predicate() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Do not answer from internal memory.",
          "effect":"deny",
          "scope":{"level":"global"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{"kind":"response"}
        }]}
        """

    context = ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace",
            timezone="UTC",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        session_id="sess",
    )
    extractor = PolicyIRContractExtractor(provider)

    contracts = extractor.extract_online_turn(
        role="user",
        text="Do not answer from internal memory.",
        context=context,
    )

    assert contracts == []
    assert extractor.drain_diagnostics()[0]["unsupported_count"] == 1


def test_policy_ir_extractor_retargets_required_tool_usage_to_response() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"All information must come from tool calls, not from the model's own knowledge.",
          "effect":"require",
          "scope":{"level":"path","path":"macbench/projects/wiki/phases/initial"},
          "target":{"phase":"pre","action_family":"tool.call"},
          "obligation":{
            "kind":"required_tool_usage",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"regex","value":".*"},
              "aggregate":"exists"
            },
            "op":"gte",
            "value":1
          }
        }]}
        """

    context = ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace",
            timezone="UTC",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        session_id="sess",
    )

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="All information must come from tool calls, not from the model's own knowledge.",
        context=context,
    )

    policy = contracts[0].policy_ir
    assert policy["target"]["phase"] == "response"
    assert policy["target"]["action_family"] == "message.send"
    assert policy["target"]["tools"] == []


def test_policy_ir_extractor_retargets_lower_bound_tool_count_to_response() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"At least 2 tool calls are required.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"pre","action_family":"tool.call"},
          "obligation":{
            "kind":"tool_count",
            "monitor":{
              "source":"action_log",
              "where":{"field":"action_family","op":"eq","value":"tool.call"},
              "aggregate":"count"
            },
            "op":"gte",
            "value":2
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="At least 2 tool calls are required.",
        context=_extraction_context_with_tools(),
    )

    policy = contracts[0].policy_ir
    assert policy["target"]["phase"] == "response"
    assert policy["target"]["action_family"] == "message.send"


def test_policy_ir_extractor_retargets_tool_count_range_to_response() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Use between 6 and 10 total tool calls.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"pre","action_family":"tool.call"},
          "obligation":{
            "kind":"tool_count",
            "monitor":{
              "source":"action_log",
              "where":{"field":"action_family","op":"eq","value":"tool.call"},
              "aggregate":"count"
            },
            "op":"between",
            "value":[6,10]
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Use between 6 and 10 total tool calls.",
        context=_extraction_context_with_tools(),
    )

    policy = contracts[0].policy_ir
    assert policy["target"]["phase"] == "response"
    assert policy["target"]["action_family"] == "message.send"


def test_policy_ir_extractor_normalizes_response_character_range() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"The final response must be between 100 and 500 characters.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"response",
            "predicate":{"field":"response","op":"word_count_lte","value":500},
            "op":"gte",
            "value":100
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="The final response must be between 100 and 500 characters.",
        context=_extraction_context_with_tools(),
    )

    predicate = contracts[0].policy_ir["obligation"]["predicate"]
    assert predicate["field"] == "response"
    assert predicate["op"] == "char_count_between"
    assert predicate["value"] == [100, 500]


def test_policy_ir_extractor_normalizes_parallel_tools_to_same_step() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Invoke city_feature_identifier and city_reputation_identifier in a single action step.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"pre","action_family":"tool.call"},
          "obligation":{
            "kind":"sequence",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"in","value":"city_feature_identifier,city_reputation_identifier"},
              "aggregate":"exists"
            }
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Invoke city_feature_identifier and city_reputation_identifier in a single action step.",
        context=_extraction_context_with_tools(),
    )

    policy = contracts[0].policy_ir
    obligation = policy["obligation"]
    assert policy["target"]["phase"] == "response"
    assert policy["target"]["action_family"] == "message.send"
    assert obligation["kind"] == "same_step"
    assert obligation["value"] == 2
    assert obligation["monitor"]["aggregate"] == "distinct_count"
    assert obligation["monitor"]["group_by"] == "turn_id"


def test_policy_ir_extractor_normalizes_same_tool_parallel_calls_to_count() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Invoke altitude_tool for Rocky Mountains and Alps in a single action step.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"sequence",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"in","value":["altitude_tool"]},
              "aggregate":"distinct_count",
              "distinct_by":"tool_name"
            },
            "value":1
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Invoke altitude_tool for Rocky Mountains and Alps in a single action step.",
        context=_extraction_context_with_tools(),
    )

    obligation = contracts[0].policy_ir["obligation"]
    assert obligation["kind"] == "same_step"
    assert obligation["value"] == 2
    assert obligation["monitor"]["aggregate"] == "count"
    assert "distinct_by" not in obligation["monitor"]


def test_policy_ir_extractor_normalizes_interaction_turn_monitor() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"At most 3 interaction turns are allowed.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"pre","action_family":"tool.call"},
          "obligation":{
            "kind":"interaction_turn_count",
            "monitor":{
              "source":"action_log",
              "where":{"field":"action_family","op":"eq","value":"message.send"},
              "aggregate":"count"
            },
            "op":"lte",
            "value":3
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="At most 3 interaction turns are allowed.",
        context=_extraction_context_with_tools(),
    )

    policy = contracts[0].policy_ir
    where = policy["obligation"]["monitor"]["where"]
    assert policy["target"]["phase"] == "response"
    assert where["field"] == "action_family"
    assert where["op"] == "in"
    assert where["value"] == ["tool.call", "message.send"]


def test_policy_ir_extractor_binds_broad_evidence_usage_to_search_tools() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"All information must come from tool calls, not memory.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"required_tool_usage",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"regex","value":".*"},
              "aggregate":"exists"
            },
            "op":"gte",
            "value":1
          }
        }]}
        """

    context = _extraction_context_with_tools()

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="All information must come from tool calls, not memory.",
        context=context,
    )

    monitor = contracts[0].policy_ir["obligation"]["monitor"]
    assert monitor["where"]["field"] == "tool_name"
    assert monitor["where"]["op"] == "in"
    assert monitor["where"]["value"] == ["historical_event_finder", "web_search"]


def test_policy_ir_extractor_keeps_specific_evidence_monitor() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Use political_successor_finder before answering.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"required_tool_usage",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"eq","value":"political_successor_finder"},
              "aggregate":"exists"
            },
            "op":"gte",
            "value":1
          }
        }]}
        """

    context = _extraction_context_with_tools()

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Use political_successor_finder before answering.",
        context=context,
    )

    monitor = contracts[0].policy_ir["obligation"]["monitor"]
    assert monitor["where"]["field"] == "tool_name"
    assert monitor["where"]["op"] == "eq"
    assert monitor["where"]["value"] == "political_successor_finder"


def test_policy_ir_extractor_splits_in_monitor_tool_string() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Use search-like tools before answering.",
          "effect":"require",
          "scope":{"level":"session"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"required_tool_usage",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"in","value":"web_search, historical_event_finder"},
              "aggregate":"exists"
            },
            "op":"gte",
            "value":1
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Use search-like tools before answering.",
        context=_extraction_context_with_tools(),
    )

    monitor = contracts[0].policy_ir["obligation"]["monitor"]
    assert monitor["where"]["value"] == ["web_search", "historical_event_finder"]


def test_policy_ir_extractor_normalizes_required_tool_usage_effect() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Do not answer from memory; use tools as the source of truth.",
          "effect":"deny",
          "scope":{"level":"global"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"required_tool_usage",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"regex","value":".*"},
              "aggregate":"exists"
            },
            "op":"gte",
            "value":1
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Do not answer from memory; use tools as the source of truth.",
        context=_extraction_context_with_tools(),
    )

    assert len(contracts) == 1
    assert contracts[0].effect == RuleEffect.REQUIRE
    assert contracts[0].policy_ir["effect"] == "require"


def test_policy_ir_extractor_converts_monitor_based_response_to_required_tool_usage() -> None:
    def provider(_prompt: str, *, system_prompt: str | None = None) -> str:
        return """
        {"policies":[{
          "text":"Do not answer from memory; use tools as the source of truth.",
          "effect":"deny",
          "scope":{"level":"global"},
          "target":{"phase":"response","action_family":"message.send"},
          "obligation":{
            "kind":"response",
            "monitor":{
              "source":"action_log",
              "where":{"field":"tool_name","op":"eq","value":".*"},
              "aggregate":"exists"
            },
            "value":1
          }
        }]}
        """

    contracts = PolicyIRContractExtractor(provider).extract_online_turn(
        role="user",
        text="Do not answer from memory; use tools as the source of truth.",
        context=_extraction_context_with_tools(),
    )

    assert len(contracts) == 1
    assert contracts[0].effect == RuleEffect.REQUIRE
    obligation = contracts[0].policy_ir["obligation"]
    assert obligation["kind"] == "required_tool_usage"
    assert obligation["monitor"]["where"]["op"] == "in"
    assert obligation["monitor"]["where"]["value"] == ["historical_event_finder", "web_search"]


def _extraction_context_with_tools() -> ExtractionContext:
    return ExtractionContext(
        normalization=NormalizationContext(
            workspace="/workspace",
            timezone="UTC",
            now=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ),
        session_id="sess",
        tool_capsule_system_prompt=render_tool_capsule_system_prompt(
            [
                ToolCapabilityCapsule(
                    name="web_search",
                    description="Search the web for evidence.",
                    input_schema={},
                ),
                ToolCapabilityCapsule(
                    name="historical_event_finder",
                    description="Find historical event records.",
                    input_schema={},
                ),
                ToolCapabilityCapsule(
                    name="send_message",
                    description="Send the final message.",
                    input_schema={},
                ),
            ]
        ),
    )
