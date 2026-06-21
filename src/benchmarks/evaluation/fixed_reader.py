from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

from dotenv import load_dotenv

from benchmarks.schemas.models import CanonicalAction, Decision


@dataclass(frozen=True)
class ReaderInput:
    qa_id: str
    current_state: dict[str, object]
    proposed_action: CanonicalAction
    retrieved_context: str
    token_budget: int = 2000


@dataclass(frozen=True)
class ReaderOutput:
    decision: Decision
    active_contract_ids: list[str]
    reason: str


class ReaderBackend(Protocol):
    def complete(self, prompt: str, *, temperature: float) -> str: ...


def load_reader_config(env_file: str | None = None) -> dict[str, str | None]:
    load_dotenv(env_file, override=False)
    return {
        "api_key": os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY"),
        "base_url": os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL"),
        "model": os.getenv("MAC_LLM_MODEL") or os.getenv("LLM_MODEL"),
    }


def render_reader_prompt(reader_input: ReaderInput) -> str:
    return (
        "Decide whether the proposed action should be allow, reject, or ask.\n"
        "Return JSON with keys: decision, active_contract_ids, reason.\n\n"
        f"Current state:\n{json.dumps(reader_input.current_state, sort_keys=True)}\n\n"
        f"Proposed action:\n{reader_input.proposed_action.model_dump_json(exclude_none=True)}\n\n"
        f"Retrieved context, capped at {reader_input.token_budget} tokens:\n"
        f"{reader_input.retrieved_context}"
    )


def parse_reader_output(raw: str) -> ReaderOutput:
    raw = _repair_trivial_json(raw)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("reader output is not valid JSON") from exc
    decision = payload.get("decision")
    if decision not in {"allow", "reject", "ask"}:
        raise ValueError("reader output has invalid decision")
    ids = payload.get("active_contract_ids") or []
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        raise ValueError("active_contract_ids must be a list of strings")
    reason = payload.get("reason") or ""
    if not isinstance(reason, str):
        raise ValueError("reason must be a string")
    return ReaderOutput(decision=decision, active_contract_ids=ids, reason=reason)


def _repair_trivial_json(raw: str) -> str:
    """Repair formatting wrappers without inferring missing labels or fields."""
    stripped = raw.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fence:
        stripped = fence.group(1).strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and start < end:
        return stripped[start : end + 1]
    return stripped


def run_fixed_reader(reader_input: ReaderInput, backend: ReaderBackend) -> ReaderOutput:
    prompt = render_reader_prompt(reader_input)
    raw = backend.complete(prompt, temperature=0.0)
    return parse_reader_output(raw)
