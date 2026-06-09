from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from memory_as_contracts.adapters.base import (
    AdapterContext,
    BaseAdapter,
    adapter_config,
    resolve_workspace_path,
)
from memory_as_contracts.extractor import CandidateJsonContractExtractor, OpenAIChatResponseProvider
from memory_as_contracts.store import ContractStore


def run_adapter_command(
    adapter: BaseAdapter,
    argv: list[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog=f"memory_as_contracts.adapters.{adapter.agent_name}")
    parser.add_argument(
        "command",
        choices=[
            "user_prompt_submit",
            "pre_tool_use",
            "post_tool_use",
            "capabilities",
        ],
    )
    args = parser.parse_args(argv)
    if args.command == "capabilities":
        _write_json(asdict(adapter.capabilities))
        return 0

    payload = _read_payload()
    context = _context_from_payload(payload)
    config = adapter.configure_runtime(context)
    store = ContractStore(_store_path(context, config))
    store.init_db()
    try:
        if args.command == "user_prompt_submit":
            user_turn = str(payload.get("prompt") or payload.get("user_turn") or "")
            output = _handle_user_prompt(adapter, store, user_turn, context)
        elif args.command == "pre_tool_use":
            output = adapter.gate_event(store, payload, context)
        else:
            output = adapter.handle_post_tool_use(store, payload, context)
        _write_json(output)
        return 0
    finally:
        store.close()


def _handle_user_prompt(
    adapter: BaseAdapter,
    store: ContractStore,
    user_turn: str,
    context: AdapterContext,
) -> dict[str, Any]:
    def extractor_factory() -> CandidateJsonContractExtractor:
        return CandidateJsonContractExtractor(OpenAIChatResponseProvider.from_env())

    handler = getattr(adapter, "handle_user_prompt_submit", None)
    if callable(handler):
        return handler(
            store,
            user_turn,
            context,
            extractor_factory=extractor_factory,
        )
    result = adapter.process_user_prompt_submit(
        store,
        user_turn,
        context,
        extractor_factory=extractor_factory,
    )
    output: dict[str, Any] = {}
    if result.prompt_text:
        output["additionalContext"] = result.prompt_text
    if result.error is not None:
        output["mac"] = {"error": result.error}
    return output


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("adapter hook payload must be a JSON object")
    return payload


def _context_from_payload(payload: dict[str, Any]) -> AdapterContext:
    workspace = str(
        payload.get("workspace")
        or payload.get("cwd")
        or os.environ.get("MAC_WORKSPACE")
        or os.getcwd()
    )
    return AdapterContext(
        workspace=workspace,
        cwd=str(payload.get("cwd") or workspace),
        repo=_optional_text(payload.get("repo")),
        branch=_optional_text(payload.get("branch")),
        session_id=str(payload.get("session_id") or "session"),
        turn_id=_optional_text(payload.get("turn_id")),
        task_id=_optional_text(payload.get("task_id")),
        user_id=_optional_text(payload.get("user_id")),
        conversation_id=_optional_text(payload.get("conversation_id")),
        organization=_optional_text(payload.get("organization")),
        timezone=str(payload.get("timezone") or "UTC"),
    )


def _store_path(context: AdapterContext, config=None) -> Path:
    effective_config = config or adapter_config(context)
    return resolve_workspace_path(effective_config.db_path, context)


def _optional_text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _write_json(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
