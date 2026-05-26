#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from memory_as_contracts.adapters import (
    AdapterContext,
    ClaudeCodeAdapter,
    CodexAdapter,
    NanobotAdapter,
    OpenClawAdapter,
)
from memory_as_contracts.extractor import (
    CandidateJsonContractExtractor,
    ExtractionContext,
    HeuristicContractExtractor,
    OpenAIChatResponseProvider,
)
from memory_as_contracts.normalizers import NormalizationContext
from memory_as_contracts.resolver import RELATION_CLASSIFICATION_SYSTEM_PROMPT, ConflictResolver
from memory_as_contracts.store import ContractStore


ADAPTERS = {
    "claude_code": ClaudeCodeAdapter,
    "codex": CodexAdapter,
    "nanobot": NanobotAdapter,
    "openclaw": OpenClawAdapter,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MAC refine traces.")
    parser.add_argument(
        "--state",
        default="memory_as_contracts_memory/worktraces/refine_state.json",
        help="Path to refine_state.json",
    )
    parser.add_argument("--memory-path", help="Only run traces for this memory path or e2e")
    parser.add_argument("--trace-id", action="append", help="Only run selected trace id(s)")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument(
        "--extractor",
        choices=("heuristic", "llm"),
        default="heuristic",
        help="Contract extraction backend (default: heuristic)",
    )
    parser.add_argument(
        "--resolver",
        choices=("heuristic", "llm"),
        default="heuristic",
        help="Conflict relation classifier backend (default: heuristic)",
    )
    args = parser.parse_args()

    state_path = Path(args.state).resolve()
    state = _unwrap(json.loads(state_path.read_text(encoding="utf-8")))
    trace_ids = set(args.trace_id or [])
    results = []
    for row in state["trace_registry"]:
        if args.memory_path and row["memory_path"] != args.memory_path:
            continue
        if trace_ids and row["trace_id"] not in trace_ids:
            continue
        trace_path = state_path.parent / "traces" / f"{row['trace_id']}.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        results.append(
            run_trace(
                trace,
                state_path.parent,
                extractor_mode=args.extractor,
                resolver_mode=args.resolver,
            )
        )

    payload = {
        "extractor_mode": args.extractor,
        "resolver_mode": args.resolver,
        "results": results,
        "aggregates": aggregate(results),
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def _build_extractor(mode: str) -> HeuristicContractExtractor | CandidateJsonContractExtractor:
    if mode == "llm":
        return CandidateJsonContractExtractor(OpenAIChatResponseProvider.from_env())
    return HeuristicContractExtractor()


def _build_resolver(store: ContractStore, mode: str) -> ConflictResolver:
    if mode == "llm":
        provider = OpenAIChatResponseProvider.from_env(
            system_prompt=RELATION_CLASSIFICATION_SYSTEM_PROMPT
        )
        return ConflictResolver(store, relation_response_provider=provider)
    return ConflictResolver(store)


def run_trace(
    trace: dict[str, Any],
    worktraces_dir: Path,
    *,
    extractor_mode: str = "heuristic",
    resolver_mode: str = "heuristic",
) -> dict[str, Any]:
    trace_id = trace["trace_id"]
    data_dir = worktraces_dir / "tmp_runs" / trace_id
    if data_dir.exists():
        shutil.rmtree(data_dir)
    data_dir.mkdir(parents=True)
    workspace = data_dir / "workspace"
    workspace.mkdir()
    store = ContractStore(data_dir / "contracts.sqlite")
    store.init_db()

    default_adapter_name = trace.get("adapter", "codex")
    adapters = {name: adapter_cls() for name, adapter_cls in ADAPTERS.items()}
    context = AdapterContext(
        workspace=str(workspace.resolve(strict=False)),
        cwd=str(workspace.resolve(strict=False)),
        repo=trace.get("repo", "repo"),
        branch=trace.get("branch", "main"),
        session_id=trace.get("session_id", trace_id),
        task_id=trace.get("task_id", "refine-task"),
        user_id=trace.get("user_id", "user-refine"),
        timezone=trace.get("timezone", "UTC"),
        now=datetime.fromisoformat(trace.get("now", "2026-05-26T00:00:00+00:00")),
    )
    extractor = _build_extractor(extractor_mode)
    resolver = _build_resolver(store, resolver_mode)

    turn_outputs: list[dict[str, Any]] = []
    for index, turn in enumerate(trace.get("turns", [])):
        role = turn.get("role", "")
        content = str(turn.get("content", ""))
        metadata = turn.get("metadata") or {}
        adapter_name = metadata.get("adapter", default_adapter_name)
        adapter = adapters[adapter_name]
        if role == "user":
            extracted = extractor.extract_online_turn(
                role="user",
                text=content,
                context=_extraction_context(context, trace_id, f"turn-{index}", adapter_name),
            )
            resolved = [result.contract for result in resolver.insert_batch(extracted)]
            turn_outputs.append(
                {
                    "turn": index,
                    "type": "extract",
                    "extracted": [contract_summary(contract) for contract in resolved],
                }
            )
        if metadata.get("tool_name") or metadata.get("toolName"):
            tool_name = metadata.get("tool_name", metadata.get("toolName"))
            event = {
                "tool_name": tool_name,
                "toolName": tool_name,
                "name": tool_name,
                "tool_input": metadata.get("tool_input", {}),
                "arguments": metadata.get("tool_input", {}),
                "params": metadata.get("tool_input", {}),
                "intent": metadata.get("intent", content),
                "session_id": metadata.get("session_id", context.session_id),
                "turn_id": f"turn-{index}",
            }
            payload = _gate(adapter_name, adapter, store, event, context)
            turn_outputs.append({"turn": index, "type": "gate", "payload": payload})

    query_results = []
    for query in trace.get("recall_queries", []):
        probe = query.get("probe") or {}
        adapter_name = probe.get("adapter", default_adapter_name)
        output = run_probe(query, adapter_name, adapters[adapter_name], store, context)
        item_results = [
            {
                "value": item["value"],
                "matched": match_item(output, item),
                "matcher": item.get("matcher", "substring"),
            }
            for item in query.get("expected_information", [])
        ]
        coverage = (
            sum(1 for item in item_results if item["matched"]) / len(item_results)
            if item_results
            else 0.0
        )
        query_results.append(
            {
                "query": query.get("query", ""),
                "output": output,
                "support_coverage": coverage,
                "query_success": 1.0 if coverage == 1.0 else 0.0,
                "items": item_results,
            }
        )

    support = (
        sum(result["support_coverage"] for result in query_results) / len(query_results)
        if query_results
        else 0.0
    )
    success = (
        sum(result["query_success"] for result in query_results) / len(query_results)
        if query_results
        else 0.0
    )
    contracts = [contract_summary(contract) for contract in store.list_contracts()]
    receipts = [receipt.model_dump(mode="json") for receipt in store.list_receipts()]
    store.close()
    return {
        "trace_id": trace_id,
        "memory_path": trace.get("memory_path", "adapter_working_contract_flow"),
        "extractor_mode": extractor_mode,
        "resolver_mode": resolver_mode,
        "eval_mode": trace.get("eval_mode", "qa"),
        "support_coverage": round(support, 4),
        "query_success": round(success, 4),
        "queries": query_results,
        "turn_outputs": turn_outputs,
        "contracts": contracts,
        "receipts": receipts,
    }


def run_probe(
    query: dict[str, Any],
    adapter_name: str,
    adapter: Any,
    store: ContractStore,
    context: AdapterContext,
) -> str:
    probe = query.get("probe") or {"type": "contracts"}
    probe_type = probe.get("type", "contracts")
    if probe_type == "prompt":
        user_turn = str(probe.get("user_turn") or query.get("query") or "")
        if adapter_name in {"claude_code", "codex"}:
            return _dump(adapter.handle_user_prompt_submit(store, user_turn, context))
        if adapter_name == "nanobot":
            return _dump(adapter.build_observability_prompt_context(store, user_turn, context))
        if adapter_name == "openclaw":
            return _dump(adapter.bridge_before_prompt_build(store, {"prompt": user_turn}, context))
        return adapter.render_prompt_context(store, user_turn, context)
    if probe_type == "gate":
        event = {
            "tool_name": probe.get("tool_name", "exec"),
            "toolName": probe.get("tool_name", "exec"),
            "name": probe.get("tool_name", "exec"),
            "tool_input": probe.get("tool_input", {}),
            "arguments": probe.get("tool_input", {}),
            "params": probe.get("tool_input", {}),
            "intent": probe.get("intent", query.get("query", "")),
        }
        return _dump(_gate(adapter_name, adapter, store, event, context))
    if probe_type == "receipts":
        return _dump([receipt.model_dump(mode="json") for receipt in store.list_receipts()])
    return _dump([contract_summary(contract) for contract in store.list_contracts()])


def _gate(
    adapter_name: str,
    adapter: Any,
    store: ContractStore,
    event: dict[str, Any],
    context: AdapterContext,
) -> dict[str, Any]:
    try:
        if adapter_name == "openclaw":
            return adapter.bridge_before_tool_call(store, event, context)
        return adapter.gate_event(store, event, context)
    except Exception as exc:  # noqa: BLE001 - the runner scores adapter-surface failures.
        return {
            "error": type(exc).__name__,
            "message": str(exc),
            "event": event,
        }


def _extraction_context(
    context: AdapterContext, conversation_id: str, turn_id: str, adapter_name: str
) -> ExtractionContext:
    return ExtractionContext(
        normalization=NormalizationContext(
            workspace=str(context.workspace_path()),
            repo=context.repo,
            task=context.task_id,
            agent_family=[adapter_name],
            user_id=context.user_id,
            timezone=context.timezone,
            now=context.current_time(),
        ),
        conversation_id=conversation_id,
        turn_id=turn_id,
    )


def contract_summary(contract: Any) -> dict[str, Any]:
    return {
        "id": contract.id,
        "text": contract.text,
        "kind": contract.kind.value,
        "status": contract.status.value,
        "scope": contract.scope.model_dump(mode="json"),
        "lifecycle": contract.lifecycle.model_dump(mode="json"),
        "constraints": contract.action_constraints.model_dump(mode="json"),
    }


def match_item(output: str, item: dict[str, Any]) -> bool:
    expected = str(item.get("value", ""))
    matcher = item.get("matcher", "substring")
    if matcher == "regex":
        return re.search(expected, output, flags=re.I | re.S) is not None
    if matcher == "exact":
        return output.strip() == expected
    return expected.lower() in output.lower()


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        grouped.setdefault(result["memory_path"], []).append(result)
    return {
        path: {
            "support_coverage": round(
                sum(item["support_coverage"] for item in items) / len(items), 4
            ),
            "query_success": round(
                sum(item["query_success"] for item in items) / len(items), 4
            ),
            "trace_count": len(items),
        }
        for path, items in grouped.items()
    }


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _unwrap(data: dict[str, Any]) -> dict[str, Any]:
    inner = data.get("refine_state")
    return inner if isinstance(inner, dict) else data


if __name__ == "__main__":
    raise SystemExit(main())
