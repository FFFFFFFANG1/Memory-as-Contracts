#!/usr/bin/env python3
"""Run AutoMemory critic-style traces against the current MAC kernel.

The traces in this directory are grey-box scenarios: they exercise public MAC
component boundaries and score observable outcomes rather than private helpers.
They are intended as a first-pass effectiveness check, not a replacement for
the unit test suite.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if sys.version_info < (3, 11):
    raise SystemExit("MAC trace runner requires Python 3.11+. Run with: UV_CACHE_DIR=.uv-cache uv run python automemory/run_traces.py")

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from memory_as_contracts.adapters import AdapterContext, CodexAdapter
from memory_as_contracts.compiler import PolicyCompiler
from memory_as_contracts.extractor import (
    CandidateJsonContractExtractor,
    HeuristicContractExtractor,
    OpenAIChatResponseProvider,
)
from memory_as_contracts.gate import ActionGate, ExcludedActionPattern
from memory_as_contracts.models import (
    ActionLogEntryV1,
    ActionOutcome,
    ArgPattern,
    Contract,
    ContractEdge,
    ContractKind,
    ContractSource,
    EdgeRelation,
    GateDecisionType,
    Lifecycle,
    LifecycleType,
    Modality,
    PredicateStatus,
    RuleEffect,
    RuleSemantics,
    Scope,
    ScopeLevel,
    SourceKind,
    Strength,
    ToolPattern,
    ValidatorEnforcementShape,
    ValidatorVersion,
)
from memory_as_contracts.retrieval import PromptIntakeRetriever, PromptRetrievalContext
from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext
from memory_as_contracts.store import ContractStore
from memory_as_contracts.validator_dispatch import validator_scope_key_for_signature
from memory_as_contracts.validator_installation import ValidatorInstaller
from memory_as_contracts.validator_generation import (
    VALIDATOR_GENERATION_SYSTEM_PROMPT,
    ValidatorSnippetGenerator,
)
from memory_as_contracts.validators import ValidatorRuntime


NOW = datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc)
USE_LLM = False
INCLUDE_OUTPUTS = False


@dataclass
class CheckResult:
    name: str
    passed: bool
    actual: Any
    expected: Any


@dataclass
class InstalledValidator:
    version: ValidatorVersion
    package: Any


def env_file() -> Path:
    return REPO_ROOT / ".env"


def extraction_response_provider() -> OpenAIChatResponseProvider:
    return OpenAIChatResponseProvider.from_env(env_file())


def validator_response_provider() -> OpenAIChatResponseProvider:
    return OpenAIChatResponseProvider.from_env(
        env_file(),
        system_prompt=VALIDATOR_GENERATION_SYSTEM_PROMPT,
    )


def extractor_factory():
    if USE_LLM:
        return CandidateJsonContractExtractor(extraction_response_provider())
    return HeuristicContractExtractor()


def validator_generator_factory():
    if not USE_LLM:
        return None
    return ValidatorSnippetGenerator(validator_response_provider())


def tool_capsules_for_contract(contract: Contract) -> list[dict[str, Any]]:
    names = {
        pattern.tool
        for pattern in [*contract.tool_patterns, *contract.check_patterns, *contract.update_patterns]
        if pattern.tool
    }
    return [
        {
            "name": name,
            "description": f"Trace-local tool capsule for {name}.",
            "input_schema": {"type": "object"},
        }
        for name in sorted(names)
    ]


def make_store() -> ContractStore:
    store = ContractStore(":memory:")
    store.init_db()
    return store


def source(span: str, kind: SourceKind = SourceKind.USER_TURN) -> ContractSource:
    return ContractSource(kind=kind, span=span, created_at=NOW)


def project_scope(workspace: str = "/workspace/project", repo: str = "project") -> Scope:
    return Scope(level=ScopeLevel.PROJECT, workspace=workspace, repo=repo)


def path_scope(path_glob: str, workspace: str = "/workspace/project", repo: str = "project") -> Scope:
    return Scope(level=ScopeLevel.PATH, workspace=workspace, repo=repo, path_globs=[path_glob])


def task_scope(task: str = "task-1", workspace: str = "/workspace/project") -> Scope:
    return Scope(level=ScopeLevel.TASK, workspace=workspace, repo="project", task=task)


def contract_from_spec(spec: dict[str, Any]) -> Contract:
    return Contract(
        id=spec["id"],
        text=spec["text"],
        effect=RuleEffect(spec.get("effect", "deny")),
        kind=ContractKind(spec.get("kind", "prohibition")),
        modality=Modality(spec.get("modality", "MUST_NOT")),
        strength=Strength(spec.get("strength", "hard")),
        source=source(spec.get("source_span", spec["text"]), SourceKind(spec.get("source_kind", "user_turn"))),
        scope=Scope.model_validate(spec["scope"]),
        lifecycle=Lifecycle.model_validate(spec.get("lifecycle", {"type": "until_revoked", "until_revoked": True})),
        semantics=RuleSemantics.model_validate(spec.get("semantics", {})),
        tool_patterns=[ToolPattern.model_validate(item) for item in spec.get("tool_patterns", [])],
        validator_enforcement_shape=ValidatorEnforcementShape(
            spec.get("validator_enforcement_shape", "no_validator")
        ),
        check_patterns=[ToolPattern.model_validate(item) for item in spec.get("check_patterns", [])],
        update_patterns=[ToolPattern.model_validate(item) for item in spec.get("update_patterns", [])],
        state_fields=list(spec.get("state_fields", [])),
    )


def install_pattern_contract(store: ContractStore, contract: Contract) -> Contract:
    stored = store.add_contract(contract)
    if stored.tool_patterns:
        store.install_rule_pattern_version(PolicyCompiler().compile(stored))
    return stored


def build_signature(event: dict[str, Any], context: dict[str, Any] | None = None):
    ctx = context or {}
    return ActionSignatureBuilder().build(
        tool_name=event["tool_name"],
        raw_arguments=event.get("arguments", {}),
        intent=event.get("intent", ""),
        context=SignatureContext(
            host=ctx.get("host", "codex"),
            agent_family=ctx.get("agent_family", "codex"),
            session_id=ctx.get("session_id", "sess-1"),
            task_id=ctx.get("task_id", "task-1"),
            turn_id=ctx.get("turn_id"),
            user_id=ctx.get("user_id", "user-1"),
            cwd=ctx.get("workspace", "/workspace/project"),
            workspace=ctx.get("workspace", "/workspace/project"),
            repo=ctx.get("repo", "project"),
            branch=ctx.get("branch", "main"),
            now=NOW,
        ),
    )


def parse_dt(value: Any) -> Any:
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def adapter_context_from_spec(spec: dict[str, Any], **updates: Any) -> AdapterContext:
    payload = {**spec, **updates}
    if "now" in payload:
        payload["now"] = parse_dt(payload["now"])
    return AdapterContext(**payload)


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), sort_keys=True)
    return json.dumps(value, sort_keys=True, default=str)


def match(actual: Any, expected: Any) -> bool:
    matcher = expected.get("matcher", "equals")
    value = expected.get("value")
    if matcher == "equals":
        return actual == value
    if matcher == "contains":
        return str(value).lower() in as_text(actual).lower()
    if matcher == "regex":
        return re.search(str(value), as_text(actual), re.I | re.S) is not None
    if matcher == "one_of":
        return actual in value
    if matcher == "length":
        return len(actual) == int(value)
    if matcher == "gte":
        return float(actual) >= float(value)
    if matcher == "not_contains":
        return str(value).lower() not in as_text(actual).lower()
    raise ValueError(f"unknown matcher: {matcher}")


def get_path(obj: Any, path: str) -> Any:
    current = obj
    for part in path.split("."):
        if part == "":
            continue
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part)
    return current


def evaluate_assertions(outputs: dict[str, Any], assertions: list[dict[str, Any]]) -> list[CheckResult]:
    results: list[CheckResult] = []
    for assertion in assertions:
        actual = get_path(outputs, assertion["path"])
        expected = assertion["expected"]
        results.append(
            CheckResult(
                name=assertion["name"],
                passed=match(actual, expected),
                actual=actual,
                expected=expected,
            )
        )
    return results


def install_contracts_from_trace(store: ContractStore, trace: dict[str, Any]) -> None:
    for spec in trace.get("contracts", []):
        install_pattern_contract(store, contract_from_spec(spec))
    for edge_spec in trace.get("edges", []):
        store.add_edge(
            ContractEdge(
                from_contract=edge_spec["from_contract"],
                to_contract=edge_spec["to_contract"],
                relation=EdgeRelation(edge_spec["relation"]),
                scope=Scope.model_validate(edge_spec["scope"]),
                lifecycle=Lifecycle.model_validate(
                    edge_spec.get("lifecycle", {"type": "bounded_task", "trigger_event": "task_complete"})
                ),
                source=source(edge_spec.get("source_span", "trace edge"), SourceKind.AGENT_INFERRED),
            )
        )


def run_prompt_retrieval(trace: dict[str, Any]) -> dict[str, Any]:
    store = make_store()
    install_contracts_from_trace(store, trace)
    context = PromptRetrievalContext(**trace["prompt_context"])
    packets = PromptIntakeRetriever(store).retrieve(context)
    rendered = PromptIntakeRetriever(store).render_prompt_text(packets)
    return {
        "packet_ids": [packet.id for packet in packets],
        "packet_channels": [packet.channel for packet in packets],
        "rendered": rendered,
    }


def run_gate(trace: dict[str, Any]) -> dict[str, Any]:
    store = make_store()
    install_contracts_from_trace(store, trace)
    gate = ActionGate(
        store,
        exclude_actions=[
            ExcludedActionPattern(**item) if isinstance(item, dict) else item
            for item in trace.get("exclude_actions", [])
        ],
    )
    decisions: dict[str, Any] = {}
    for event in trace["events"]:
        result = gate.gate(build_signature(event, event.get("context")))
        decisions[event["id"]] = {
            "decision": result.decision.decision.value,
            "reason": result.decision.reason,
            "contracts_used": result.receipt.contracts_used,
            "contracts_ignored": [item.model_dump(mode="json") for item in result.receipt.contracts_ignored],
            "edges_applied": result.receipt.edges_applied,
            "receipt_result": result.receipt.result,
        }
    return decisions


def run_conflict_resolution(trace: dict[str, Any]) -> dict[str, Any]:
    from memory_as_contracts.resolver import ConflictResolver

    store = make_store()
    for spec in trace.get("seed_contracts", []):
        store.add_contract(contract_from_spec(spec))
    inserted = []
    for spec in trace.get("candidate_contracts", []):
        result = ConflictResolver(store).insert(contract_from_spec(spec))
        inserted.append(
            {
                "contract_id": result.contract.id,
                "relation": result.relation.value,
                "status": store.get_contract(result.contract.id).status.value,
            }
        )
    return {
        "inserted": inserted,
        "contract_status": {contract.id: contract.status.value for contract in store.list_contracts()},
        "edges": [
            {
                "from_contract": edge.from_contract,
                "to_contract": edge.to_contract,
                "relation": edge.relation.value,
                "scope": edge.scope.model_dump(mode="json"),
            }
            for edge in store.list_edges()
        ],
    }


def run_online_ingestion(trace: dict[str, Any]) -> dict[str, Any]:
    store = make_store()
    adapter = CodexAdapter(online_extractor_factory=extractor_factory)
    ctx_spec = trace["adapter_context"]
    workspace = Path(ctx_spec["workspace"])
    workspace.mkdir(parents=True, exist_ok=True)
    context = adapter_context_from_spec(ctx_spec)
    extracted_batches = []
    prompt_text = ""
    for i, turn in enumerate(trace["turns"], start=1):
        turn_context = adapter_context_from_spec(ctx_spec, turn_id=f"u-{i:03d}")
        result = adapter.process_user_prompt_submit(
            store,
            turn["content"],
            turn_context,
            extractor_factory=extractor_factory,
        )
        if result.extracted_contracts:
            extracted_batches.append([contract.id for contract in result.extracted_contracts])
        prompt_text = result.prompt_text
    return {
        "contract_count": len(store.list_contracts()),
        "contract_texts": [contract.text for contract in store.list_contracts()],
        "contracts": [contract.model_dump(mode="json") for contract in store.list_contracts()],
        "statuses": {contract.id: contract.status.value for contract in store.list_contracts()},
        "pending_turns": len(store.pending_user_turns(adapter_id="codex", session_id=context.session_id, limit=20)),
        "extracted_batches": extracted_batches,
        "prompt_text": prompt_text,
    }


def run_adapter_cold_start(trace: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp) / "project"
        workspace.mkdir()
        for file_spec in trace["files"]:
            path = workspace / file_spec["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(file_spec["content"], encoding="utf-8")
        store = make_store()
        adapter = CodexAdapter(online_extractor_factory=extractor_factory)
        context = AdapterContext(
            workspace=str(workspace),
            cwd=str(workspace),
            repo="project",
            session_id="sess-cold",
            task_id="task-cold",
            user_id="user-1",
            now=NOW,
        )
        extracted = adapter.cold_start_import(store, extractor_factory(), context)
        prompt = adapter.render_prompt_context(store, trace["user_turn"], context)
        web_result = adapter.gate_event(
            store,
            {
                "tool_name": "web.search",
                "tool_input": {"query": "library docs"},
                "session_id": "sess-cold",
                "intent": "look up external docs",
            },
            context,
        )
        return {
            "extracted_count": len(extracted),
            "contract_texts": [contract.text for contract in store.list_contracts()],
            "contracts": [contract.model_dump(mode="json") for contract in store.list_contracts()],
            "snapshot_count": len(store.list_source_snapshots()),
            "prompt_text": prompt,
            "web_gate_decision": web_result["mac"]["decision"],
        }


CHECK_ONLY_SNIPPET = """
def update(state, entry, log, context):
    return state

def check(action, state, log, context):
    rows = log.search({
        "from": "actions",
        "select": ["seq", "result_text"],
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


BUDGET_SNIPPET = """
def _amount_cents(payload):
    arguments = payload.get("arguments") or {}
    result = payload.get("result") or {}
    candidates = [arguments.get("amount"), arguments.get("price"), arguments.get("total")]
    if isinstance(result, dict):
        candidates.extend([result.get("amount"), result.get("price"), result.get("total")])
    for item in arguments.get("items") or []:
        candidates.extend([item.get("amount"), item.get("price")])
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
    seq = entry["seq"]
    if seq in state["seen_entry_seqs"]:
        return state
    amount = _amount_cents(entry)
    if amount is not None:
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


ASK_SNIPPET = """
def check(action, state, log, context):
    if context.get("ask_response_flag"):
        return allow("User response observed for this pending action.")
    return ask("Ask the user before sending the notification.")
"""


def install_validator(
    store: ContractStore,
    contract: Contract,
    snippet: str,
    initial_state: dict[str, Any],
    *,
    pending_examples: list[dict[str, Any]] | None = None,
    committed_examples: list[ActionLogEntryV1] | None = None,
) -> InstalledValidator:
    stored = store.add_contract(contract)
    pending = pending_examples or [
        {
            "tool_name": (stored.check_patterns[0].tool if stored.check_patterns else "Bash"),
            "host_action": stored.semantics.actions[0] if stored.semantics.actions else "exec",
            "arguments": {"command": "git push origin main"},
        }
    ]
    committed = committed_examples or []
    if USE_LLM:
        generator = validator_generator_factory()
        assert generator is not None
        package = generator.generate_verified(
            stored,
            store=store,
            session_id="sess-1",
            task_id="task-1",
            pending_examples=pending,
            tool_capsules=tool_capsules_for_contract(stored),
        )
    else:
        package = {"status": "ready", "snippet": snippet, "initial_state": initial_state}
    result = ValidatorInstaller().install(
        stored,
        package,
        store=store,
        session_id="sess-1",
        task_id="task-1",
        pending_examples=pending,
        committed_examples=committed,
    )
    if result.status != "installed" or result.validator_version is None:
        raise AssertionError(f"validator installation failed: {result.errors}")
    return InstalledValidator(version=result.validator_version, package=package)


def run_validator_check_only(trace: dict[str, Any]) -> dict[str, Any]:
    store = make_store()
    contract = contract_from_spec(trace["contract"])
    pending = [{
        "tool_name": trace["pending_action"]["tool_name"],
        "host_action": "exec",
        "arguments": trace["pending_action"].get("arguments", {}),
    }]
    installed = install_validator(
        store,
        contract,
        CHECK_ONLY_SNIPPET,
        {},
        pending_examples=pending,
    )
    version = installed.version
    signature = build_signature(trace["pending_action"], trace.get("context"))
    before = ActionGate(store).gate(signature)
    store.add_action_log_entry(
        ActionLogEntryV1(
            adapter_id="codex",
            session_id="sess-1",
            task_id="task-1",
            agent_id="codex",
            tool_call_id="test-run-1",
            tool_name="Bash",
            host_action="exec",
            arguments={"command": "uv run pytest -q"},
            result_text="91 passed",
            outcome=ActionOutcome.SUCCESS,
            timestamp=NOW,
            workspace="/workspace/project",
            repo="project",
        )
    )
    after = ActionGate(store).gate(signature)
    return {
        "validator_id": version.id,
        "validator": version.model_dump(mode="json"),
        "generated_package": (
            installed.package.model_dump(mode="json")
            if hasattr(installed.package, "model_dump")
            else installed.package
        ),
        "contract": store.get_contract(contract.id).model_dump(mode="json"),
        "before_decision": before.decision.decision.value,
        "before_verdicts": before.receipt.validator_verdicts,
        "after_decision": after.decision.decision.value,
        "after_verdicts": after.receipt.validator_verdicts,
    }


def run_validator_budget(trace: dict[str, Any]) -> dict[str, Any]:
    store = make_store()
    committed_examples = [
        ActionLogEntryV1(
            adapter_id="codex",
            session_id="sess-1",
            task_id="task-1",
            agent_id="codex",
            tool_call_id=f"generator-example-{i}",
            tool_name=action["tool_name"],
            host_action=action["host_action"],
            arguments=action["arguments"],
            result_text=action.get("result_text", ""),
            outcome=ActionOutcome.SUCCESS,
            timestamp=NOW,
            workspace="/workspace/project",
            repo="project",
        )
        for i, action in enumerate(trace["committed_actions"], start=1)
    ]
    if USE_LLM:
        for entry in committed_examples:
            store.add_action_log_entry(entry)
    pending = [{
        "tool_name": trace["pending_action"]["tool_name"],
        "host_action": "purchase",
        "arguments": trace["pending_action"].get("arguments", {}),
    }]
    installed = install_validator(
        store,
        contract_from_spec(trace["contract"]),
        BUDGET_SNIPPET,
        trace["initial_state"],
        pending_examples=pending,
        committed_examples=committed_examples,
    )
    version = installed.version
    runtime = ValidatorRuntime(store)
    recorded = []
    for i, action in enumerate(trace["committed_actions"], start=1):
        entry = ActionLogEntryV1(
            adapter_id="codex",
            session_id="sess-1",
            task_id="task-1",
            agent_id="codex",
            tool_call_id=f"purchase-{i}",
            tool_name=action["tool_name"],
            host_action=action["host_action"],
            arguments=action["arguments"],
            result_text=action.get("result_text", ""),
            outcome=ActionOutcome.SUCCESS,
            timestamp=NOW,
            workspace="/workspace/project",
            repo="project",
        )
        recorded.append(runtime.record_committed_action(entry).seq)
    pending = build_signature(trace["pending_action"], trace.get("context"))
    verdict = runtime.check(version, pending)
    scope_key = validator_scope_key_for_signature(store.get_contract(version.contract_id), pending)
    state = store.get_validator_state(version.id, scope_key)
    return {
        "recorded_seqs": recorded,
        "validator": version.model_dump(mode="json"),
        "generated_package": (
            installed.package.model_dump(mode="json")
            if hasattr(installed.package, "model_dump")
            else installed.package
        ),
        "contract": store.get_contract(version.contract_id).model_dump(mode="json"),
        "state": state.state if state else {},
        "state_revision": state.revision if state else None,
        "verdict": verdict.model_dump(mode="json"),
    }


def run_adapter_ask_flow(trace: dict[str, Any]) -> dict[str, Any]:
    store = make_store()
    adapter = CodexAdapter()
    context = AdapterContext(
        workspace="/workspace/project",
        cwd="/workspace/project",
        repo="project",
        session_id="sess-1",
        task_id="task-1",
        user_id="user-1",
        now=NOW,
    )
    installed = install_validator(
        store,
        contract_from_spec(trace["contract"]),
        ASK_SNIPPET,
        {},
        pending_examples=[
            {
                "tool_name": "message.send",
                "host_action": "message.send",
                "arguments": {"channel": "slack", "text": "Deploy finished"},
            }
        ],
    )
    version = installed.version
    event = {
        "tool_name": "message.send",
        "tool_input": {"channel": "slack", "text": "Deploy finished"},
        "session_id": "sess-1",
        "intent": "notify Slack",
    }
    first = adapter.handle_pre_tool_use(store, event, context)
    responded_context = AdapterContext(**{**context.__dict__, "turn_id": "u-ask"})
    adapter.observe_user_input(store, responded_context)
    second = adapter.handle_pre_tool_use(store, {**event, "turn_id": "u-ask"}, context)
    return {
        "validator_id": version.id,
        "validator": version.model_dump(mode="json"),
        "generated_package": (
            installed.package.model_dump(mode="json")
            if hasattr(installed.package, "model_dump")
            else installed.package
        ),
        "contract": store.get_contract(version.contract_id).model_dump(mode="json"),
        "first_permission": first["hookSpecificOutput"].get("permissionDecision", "allow"),
        "first_decision": first["mac"]["decision"],
        "first_requires_user_input": first["mac"].get("requires_user_input", False),
        "second_decision": second["mac"]["decision"],
        "ask_statuses": [request.status.value for request in store.list_ask_requests()],
    }


def run_e2e_contract_flow(trace: dict[str, Any]) -> dict[str, Any]:
    store = make_store()
    adapter = CodexAdapter(
        online_extractor_factory=extractor_factory,
        validator_generator_factory=validator_generator_factory,
    )
    ctx_spec = trace["adapter_context"]
    Path(ctx_spec["workspace"]).mkdir(parents=True, exist_ok=True)
    prompt_text = ""
    for i, turn in enumerate(trace["turns"], start=1):
        context = adapter_context_from_spec(ctx_spec, turn_id=f"u-{i:03d}")
        result = adapter.process_user_prompt_submit(
            store,
            turn["content"],
            context,
            extractor_factory=extractor_factory,
        )
        prompt_text = result.prompt_text
    context = adapter_context_from_spec(ctx_spec)
    gate_outputs: dict[str, Any] = {}
    for event in trace["events"]:
        payload = adapter.handle_pre_tool_use(store, event, context)
        gate_outputs[event["id"]] = {
            "decision": payload["mac"]["decision"],
            "contracts_used": payload["mac"].get("contracts_used", []),
            "permission": payload.get("hookSpecificOutput", {}).get("permissionDecision", "allow"),
        }
    return {
        "contract_texts": [contract.text for contract in store.list_contracts()],
        "contracts": [contract.model_dump(mode="json") for contract in store.list_contracts()],
        "receipt_count": len(store.list_receipts()),
        "prompt_text": prompt_text,
        "gates": gate_outputs,
    }


RUNNERS = {
    "prompt_retrieval": run_prompt_retrieval,
    "gate": run_gate,
    "conflict_resolution": run_conflict_resolution,
    "online_ingestion": run_online_ingestion,
    "adapter_cold_start": run_adapter_cold_start,
    "validator_check_only": run_validator_check_only,
    "validator_budget": run_validator_budget,
    "adapter_ask_flow": run_adapter_ask_flow,
    "e2e_contract_flow": run_e2e_contract_flow,
}


def run_trace(path: Path) -> dict[str, Any]:
    trace = json.loads(path.read_text(encoding="utf-8"))
    outputs = RUNNERS[trace["driver"]](trace)
    checks = evaluate_assertions(outputs, trace["assertions"])
    passed = sum(1 for check in checks if check.passed)
    score = passed / len(checks) if checks else 0.0
    return {
        "trace_id": trace["trace_id"],
        "memory_path": trace.get("memory_path", "unknown"),
        "description": trace.get("description", ""),
        "score": score,
        "passed": passed,
        "total": len(checks),
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "actual": check.actual,
                "expected": check.expected,
            }
            for check in checks
        ],
        "outputs": outputs if (INCLUDE_OUTPUTS or trace.get("include_outputs", False)) else None,
    }


def main() -> int:
    global USE_LLM, INCLUDE_OUTPUTS
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", type=Path, default=Path(__file__).parent / "traces")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use live LLM extractor and validator coder from .env instead of deterministic fixtures.",
    )
    parser.add_argument(
        "--include-outputs",
        action="store_true",
        help="Include raw trace outputs such as generated validator snippets and extracted rules.",
    )
    parser.add_argument("--output", type=Path, help="Write JSON report to this path.")
    args = parser.parse_args()
    USE_LLM = args.llm
    INCLUDE_OUTPUTS = args.include_outputs

    results = [run_trace(path) for path in sorted(args.trace_dir.glob("trace_id_*.json"))]
    summary = {
        "llm_mode": USE_LLM,
        "trace_count": len(results),
        "mean_score": sum(item["score"] for item in results) / len(results) if results else 0.0,
        "all_passed": all(item["score"] == 1.0 for item in results),
        "results": results,
    }
    if args.json:
        payload = json.dumps(summary, indent=2, sort_keys=True, default=str)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        print(payload)
    else:
        for item in results:
            status = "PASS" if item["score"] == 1.0 else "FAIL"
            print(f"{status} {item['trace_id']} score={item['score']:.2f} ({item['passed']}/{item['total']})")
            for check in item["checks"]:
                if not check["passed"]:
                    print(f"  - {check['name']}: actual={check['actual']!r} expected={check['expected']!r}")
        print(f"mean_score={summary['mean_score']:.2f} traces={summary['trace_count']}")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
