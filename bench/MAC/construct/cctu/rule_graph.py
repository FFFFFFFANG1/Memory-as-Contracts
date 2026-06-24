#!/usr/bin/env python3
"""Generate per-constraint scoped constraint histories for MACBench.

This stage operates independently for each selected CCTU constraint. It asks
an LLM to generate same-domain noisy companion constraints for an anchor
constraint. Graph construction and validation are handled by graph_validation.py.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_ENV_FILE = Path("bench/.env")

AnchorRole = Literal["global", "project", "task", "exception"]
ScopeName = Literal["global", "project", "phase"]

ROLE_WEIGHTS: dict[AnchorRole, float] = {
    "global": 0.20,
    "project": 0.40,
    "task": 0.25,
    "exception": 0.15,
}

ALLOWED_SCOPES = {"global", "project", "phase"}

# --- LLM prompts (edit below) ---

SYSTEM_PROMPT = """
You are reconstructing the constraint history of a long-running AI agent for MACBench.

Picture how the agent works over its lifetime. It moves across many projects, and
inside each project it moves through different phases of work. Along the way it
keeps picking up constraints: rules it must obey at runtime. Every constraint has
two parts: a semantic requirement (what to do) and a scope (where that rule
applies). A constraint is only "active" while the agent's current work sits inside
its scope. The moment the agent leaves that scope, the constraint goes silent.

Scope, from broadest to narrowest:
- global: applies to everything the agent ever does.
- project: applies only while the agent is working inside one specific project.
- phase: applies only while the agent is working inside one specific phase of a project.

You are given one anchor constraint. Imagine the agent right now, at this exact
moment in its current project and phase. At this moment the anchor must be the
ONLY active constraint.

Your job is to derive a believable history that leads to this moment: a small
tree/graph of constraints the agent has accumulated over time. Besides the anchor,
this history contains several "noisy" constraints, for example older global
defaults, rules from a different project, rules from an earlier phase, or one-off
rules whose triggering situation is already over. Every noisy constraint must be
out of scope (or otherwise overridden) at the current moment, so that when the
graph is resolved here and now, the anchor is the single constraint left standing.

How to write the constraints:
- Stay inside the same task domain as the provided task description.
- Write each constraint as a plain, standalone rule, in the same style as the
  anchor. Do not phrase it conditionally ("if", "when", "only if", "in a different
  scenario"). Put any activation context in trigger_condition instead, and use
  trigger_condition_holds to say whether that context is true at the current moment.
- Reuse introduced project and phase names when they fit the noisy constraint.
  You may introduce a new project or phase only when needed.
- Treat provided current_global_constraints as existing history. You may reference
  or override them, but do not duplicate their text verbatim as filler.
- Exactly one item is the anchor (is_anchor=true). The list is unordered, so the
  anchor may appear anywhere in it.

Return a single JSON object matching the requested output_schema. Return valid
JSON only. Do not include markdown fences.
""".strip()

ROLE_INSTRUCTIONS: dict[AnchorRole, str] = {
    "global": """
The anchor is a global default, so it stays active no matter which project or
phase the agent is in. Build the noise mostly from narrower project- or
phase-scoped constraints that belong to OTHER projects or to earlier phases, so
they are out of scope at the current moment. You may also add an older global
default that the anchor has since replaced. Do not write constraints that
contradict the anchor.
""".strip(),
    "project": """
The anchor is a project-level constraint for the agent's current project, so it
is active in the current phase. Build the noise from constraints tied to other
projects or to earlier phases of this project, and optionally one older global
default. They must all be out of scope now, leaving only the anchor active. Do
not write constraints that contradict the anchor.
""".strip(),
    "task": """
The anchor is a phase-level constraint for the agent's current phase, so it is
active right now. Build the noise from constraints that belonged to earlier
phases, to other projects, or to broader defaults that no longer apply in this
phase. They must all be out of scope now, leaving only the anchor active. Do not
write constraints that contradict the anchor.
""".strip(),
    "exception": """
The anchor is a short-lived, conditional constraint that holds only because the
current moment matches its triggering situation. Include a broader fallback
constraint that normally governs this behavior, and arrange the history so the
anchor temporarily overrides that fallback. At the current moment the anchor's
condition is satisfied (trigger_condition_holds=true) and the fallback is
suppressed, so the anchor is the only constraint left active. Put except_by on
the fallback/noisy constraint and set it to the local_id of the anchor/exception
that suppresses it.
""".strip(),
}

# Example item for output_schema.generated_constraints (one entry; repeat 5-6 noisy plus one anchor).
OUTPUT_CONSTRAINT_ITEM: dict[str, Any] = {
    "local_id": "g1",
    "text": "constraint text in the same task domain",
    "scope": "global|project|phase",
    "is_anchor": False,
    "except_by": "local_id of the exception/anchor that suppresses this constraint, or null",
    "trigger_condition": {
        "project": "specific project/application context, or null",
        "phase": "specific phase/evaluation turn context, or null",
        "occasion": "specific occasion or scenario that activates the constraint, or null",
    },
    "trigger_condition_holds": False,
}

PROMPT_REQUIREMENTS: list[str] = [
    "Return 6-7 total generated_constraints, including exactly one anchor item and 5-6 noisy non-anchor items.",
    "The anchor item must preserve the behavioral meaning of anchor_constraint.desc.",
    "Constraint text must be standalone and unconditional; do not encode activation with if/when clauses.",
    "Use trigger_condition for activation context such as project, phase, occasion, user request, or scenario.",
    "Set trigger_condition_holds=true only when that condition is satisfied at the current moment.",
    "To deactivate a noisy constraint, either make it out of scope or set except_by to the local_id of the exception/anchor that suppresses it.",
    "Do not put the anchor first by default; place it naturally among peer constraints.",
    "Use only scope values: global, project, phase.",
    "Use 'constraint' terminology, not 'memory' or 'rule'.",
    "For exception mode, include one broader fallback constraint and make the anchor trigger_condition_holds=true.",
    "At the current moment the anchor must be the only active (decisive) constraint.",
    "Stay in the same CCTU tool-use task domain; do not invent unrelated domains.",
]


def prompt_output_schema(*, anchor_role: AnchorRole, anchor_scope: ScopeName) -> dict[str, Any]:
    return {
        "anchor_role": anchor_role,
        "anchor_scope": anchor_scope,
        "generated_constraints": [OUTPUT_CONSTRAINT_ITEM],
    }


@dataclass(frozen=True)
class ConstraintJob:
    ordinal: int
    total: int
    task: dict[str, Any]
    task_index: int
    constraint: dict[str, Any]
    constraint_index: int
    anchor_role: AnchorRole


@dataclass(frozen=True)
class TaskJob:
    ordinal: int
    total: int
    task: dict[str, Any]
    task_index: int
    constraint_jobs: list[ConstraintJob]


@dataclass
class TaskGenerationContext:
    global_constraints: list[dict[str, Any]] = field(default_factory=list)
    introduced_projects: list[str] = field(default_factory=list)
    introduced_phases: list[dict[str, str | None]] = field(default_factory=list)


def load_env(env_file: Path | None = None) -> None:
    if env_file:
        load_dotenv(resolve_path(env_file), override=False)
        return

    for candidate in (DEFAULT_ENV_FILE, Path(".env")):
        path = resolve_path(candidate)
        if path.exists():
            load_dotenv(path, override=False)
            return

    load_dotenv(override=False)


def resolve_llm_config(args: argparse.Namespace) -> None:
    if not args.model:
        args.model = os.getenv("MAC_LLM_MODEL") or os.getenv("LLM_MODEL")
    if not args.base_url:
        args.base_url = (
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("MAC_LLM_BASE_URL")
            or os.getenv("LLM_BASE_URL")
        )
    if not args.api_key:
        args.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def load_output_payload(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected top-level JSON object in {path}")
    histories = payload.get("constraint_histories", [])
    if not isinstance(histories, list):
        raise ValueError(f"Expected constraint_histories array in {path}")
    return payload


def artifacts_by_constraint_uid(histories: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_uid: dict[str, dict[str, Any]] = {}
    for artifact in histories:
        if not isinstance(artifact, dict):
            continue
        uid = str(artifact.get("constraint_uid", "")).strip()
        if uid:
            by_uid[uid] = artifact
    return by_uid


def merge_constraint_histories(
    existing: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    updates_by_uid = artifacts_by_constraint_uid(updates)
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for artifact in existing:
        if not isinstance(artifact, dict):
            continue
        uid = str(artifact.get("constraint_uid", "")).strip()
        if uid in updates_by_uid:
            merged.append(updates_by_uid[uid])
            seen.add(uid)
        else:
            merged.append(artifact)
    for uid, artifact in updates_by_uid.items():
        if uid not in seen:
            merged.append(artifact)
            seen.add(uid)
    return merged


def tasks_with_constraints(tasks: list[dict[str, Any]], constraint_uids: set[str]) -> list[dict[str, Any]]:
    if not constraint_uids:
        return tasks
    selected: list[dict[str, Any]] = []
    for task in tasks:
        constraints = task.get("constraints", [])
        if not isinstance(constraints, list):
            continue
        if any(
            str(constraint.get("mac_constraint_uid", "")) in constraint_uids
            for constraint in constraints
            if isinstance(constraint, dict)
        ):
            selected.append(task)
    return selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("bench/MAC/cctu/mid_data/eval_step1_cctu.json"),
        help="CCTU step-1 dataset with mac_task_uid and mac_constraint_uid fields.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bench/MAC/cctu/mid_data/eval_step2_rule_graphs.json"),
        help="Output JSON containing generated constraint histories.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process at most N tasks.")
    parser.add_argument("--offset", type=int, default=0, help="Start from this task offset.")
    parser.add_argument("--max-constraints", type=int, default=None, help="Process at most N constraints.")
    parser.add_argument("--seed", type=int, default=13, help="Seed for reproducible anchor-role sampling.")
    parser.add_argument("--workers", type=int, default=1, help="Number of tasks to process in parallel.")
    parser.add_argument("--dry-run", action="store_true", help="Generate deterministic placeholder histories.")
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI-compatible model name. Defaults to MAC_LLM_MODEL or LLM_MODEL from bench/.env.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible base URL. Defaults to OPENAI_BASE_URL, MAC_LLM_BASE_URL, or LLM_BASE_URL.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key. Defaults to OPENAI_API_KEY or LLM_API_KEY from bench/.env.",
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument(
        "--merge-into",
        type=Path,
        default=None,
        help="Incremental mode: read this existing output file and replace entries by constraint_uid.",
    )
    parser.add_argument(
        "--only-constraint",
        action="append",
        default=[],
        help="Process only these mac_constraint_uid values; requires --merge-into for context reuse.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def selected_items(data: list[dict[str, Any]], offset: int, limit: int | None) -> list[dict[str, Any]]:
    if offset < 0:
        raise ValueError("--offset must be non-negative")
    if limit is not None and limit < 0:
        raise ValueError("--limit must be non-negative")
    end = None if limit is None else offset + limit
    return data[offset:end]


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n...[truncated]"


def evaluation_types(constraint: dict[str, Any]) -> list[str]:
    evaluations = constraint.get("evaluation", [])
    if not isinstance(evaluations, list):
        return []
    return sorted(
        {
            str(evaluation.get("type"))
            for evaluation in evaluations
            if isinstance(evaluation, dict) and evaluation.get("type")
        }
    )


def is_code_based_constraint(constraint: dict[str, Any]) -> bool:
    if "cctu_index" in constraint:
        return True
    return "code" in evaluation_types(constraint)


def task_description(task: dict[str, Any]) -> str:
    for key in ("mac_task_summary", "task_summary"):
        summary = task.get(key)
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    task_uid = task.get("mac_task_uid", task.get("id"))
    raise ValueError(f"Task {task_uid} is missing mac_task_summary")


def anchor_scope_for_role(anchor_role: AnchorRole) -> ScopeName:
    if anchor_role in {"task", "exception"}:
        return "phase"
    return anchor_role


def context_payload(context: TaskGenerationContext) -> dict[str, Any]:
    return {
        "current_global_constraints": context.global_constraints[-12:],
        "introduced_projects": context.introduced_projects[-20:],
        "introduced_phases": context.introduced_phases[-30:],
    }


def build_prompt(job: ConstraintJob, *, context: TaskGenerationContext | None = None) -> str:
    task_uid = str(job.task.get("mac_task_uid", f"task-{job.task_index:05d}"))
    constraint_uid = str(
        job.constraint.get("mac_constraint_uid", f"{task_uid}-c{job.constraint_index:04d}")
    )
    payload = {
        "task_id": job.task.get("id"),
        "cctu_id": job.task.get("cctu_id", job.task.get("id")),
        "mac_task_uid": task_uid,
        "agent_name": job.task.get("agent_name"),
        "task_description": task_description(job.task),
        "domain_context": job.task.get("domain_context"),
        "task_level": job.task.get("task_level"),
        "data_source": job.task.get("data_source"),
        "tool_names": [
            str(tool.get("name"))
            for tool in (job.task.get("tools") or [])
            if isinstance(tool, dict) and tool.get("name")
        ],
        "anchor_role": job.anchor_role,
        "anchor_scope": anchor_scope_for_role(job.anchor_role),
        "anchor_constraint": {
            "mac_constraint_uid": constraint_uid,
            "desc": job.constraint.get("desc"),
            "cctu_raw_desc": job.constraint.get("cctu_raw_desc"),
            "type": job.constraint.get("type", []),
            "cctu_primary": job.constraint.get("cctu_primary"),
            "cctu_secondary": job.constraint.get("cctu_secondary"),
            "cctu_index": job.constraint.get("cctu_index"),
            "check_path": job.constraint.get("check_path"),
            "check_artifact_type": job.constraint.get("check_artifact_type"),
            "evaluation_types": evaluation_types(job.constraint),
        },
        "task_generation_context": context_payload(context or TaskGenerationContext()),
        "role_instructions": ROLE_INSTRUCTIONS[job.anchor_role],
        "output_schema": prompt_output_schema(
            anchor_role=job.anchor_role,
            anchor_scope=anchor_scope_for_role(job.anchor_role),
        ),
        "requirements": PROMPT_REQUIREMENTS,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def call_llm(
    *,
    model: str,
    base_url: str | None,
    api_key: str | None,
    prompt: str,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> str:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise RuntimeError("openai package is required for live graph generation") from exc

    if not model:
        raise ValueError("Missing model. Pass --model or set MAC_LLM_MODEL / LLM_MODEL.")
    if not api_key:
        raise ValueError("Missing API key. Pass --api-key or set OPENAI_API_KEY / LLM_API_KEY.")

    client = openai_module.OpenAI(
        api_key=api_key,
        base_url=base_url or None,
        timeout=timeout,
        max_retries=0,
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.4,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - CLI should retry transport/provider errors.
            last_error = exc
            if attempt == retries:
                break
            time.sleep(sleep * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM request failed after {retries} attempts: {last_error}") from last_error


def parse_llm_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {exc}") from exc
    if isinstance(payload, list):
        return {"generated_constraints": payload}
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    return payload


def normalize_scope(value: Any, *, default: ScopeName) -> ScopeName:
    scope = str(value or default).strip().lower()
    if scope == "task":
        scope = "phase"
    if scope not in ALLOWED_SCOPES:
        return default
    return scope  # type: ignore[return-value]


def normalize_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "holds", "active", "satisfied"}:
            return True
        if lowered in {"false", "no", "0", "inactive", "unsatisfied", "not_satisfied"}:
            return False
    return default


def default_trigger_condition(
    *,
    item_scope: ScopeName,
    task_uid: str,
    constraint_uid: str,
    occasion: str | None,
) -> dict[str, Any]:
    return {
        "project": task_uid if item_scope in {"project", "phase"} else None,
        "phase": constraint_uid if item_scope == "phase" else None,
        "occasion": occasion,
    }


def normalize_trigger_condition(
    raw: Any,
    *,
    item_scope: ScopeName,
    task_uid: str,
    constraint_uid: str,
    fallback_occasion: str | None,
) -> dict[str, Any]:
    if isinstance(raw, dict):
        occasion = raw.get("occasion", raw.get("condition", raw.get("when", fallback_occasion)))
        project = raw.get("project")
        phase = raw.get("phase", raw.get("task"))
        return {
            "project": str(project).strip() if project not in {None, ""} else None,
            "phase": str(phase).strip() if phase not in {None, ""} else None,
            "occasion": str(occasion).strip() if occasion not in {None, ""} else None,
        }
    if isinstance(raw, str) and raw.strip():
        return default_trigger_condition(
            item_scope=item_scope,
            task_uid=task_uid,
            constraint_uid=constraint_uid,
            occasion=raw.strip(),
        )
    return default_trigger_condition(
        item_scope=item_scope,
        task_uid=task_uid,
        constraint_uid=constraint_uid,
        occasion=fallback_occasion,
    )


def clean_local_id(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text).strip("-")
    return text or fallback


def normalize_generation(
    payload: dict[str, Any],
    *,
    job: ConstraintJob,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    task_uid = str(job.task.get("mac_task_uid", f"task-{job.task_index:05d}"))
    constraint_uid = str(
        job.constraint.get("mac_constraint_uid", f"{task_uid}-c{job.constraint_index:04d}")
    )
    anchor_scope = anchor_scope_for_role(job.anchor_role)
    raw_items = payload.get("generated_constraints", [])
    if not isinstance(raw_items, list):
        raw_items = []
        warnings.append("generated_constraints missing or not a list")

    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        scope = normalize_scope(raw.get("scope"), default=anchor_scope)
        is_anchor = bool(raw.get("is_anchor", False))
        trigger_condition = normalize_trigger_condition(
            raw.get("trigger_condition"),
            item_scope=scope,
            task_uid=task_uid,
            constraint_uid=constraint_uid,
            fallback_occasion=None,
        )
        raw_trigger = raw.get("trigger_condition")
        raw_condition_holds = raw.get("trigger_condition_holds", raw.get("condition_holds"))
        if raw_condition_holds is None and isinstance(raw_trigger, dict):
            raw_condition_holds = raw_trigger.get("holds", raw_trigger.get("is_active"))
        items.append(
            {
                "local_id": clean_local_id(raw.get("local_id"), f"g{index + 1}"),
                "text": truncate_text(str(raw.get("text", "")).strip(), 1200),
                "scope": scope,
                "is_anchor": is_anchor,
                "except_by": clean_local_id(raw.get("except_by"), "")
                if raw.get("except_by")
                else None,
                "trigger_condition": trigger_condition,
                "trigger_condition_holds": normalize_bool(
                    raw_condition_holds,
                    default=is_anchor,
                ),
            }
        )

    anchor_items = [item for item in items if item["is_anchor"]]
    if len(anchor_items) != 1:
        warnings.append(f"expected exactly one anchor item, got {len(anchor_items)}; normalized")
        for item in items:
            item["is_anchor"] = False
        anchor_item = {
            "local_id": "anchor",
            "text": str(job.constraint.get("desc", "")),
            "scope": anchor_scope,
            "is_anchor": True,
            "except_by": None,
            "trigger_condition": normalize_trigger_condition(
                None,
                item_scope=anchor_scope,
                task_uid=task_uid,
                constraint_uid=constraint_uid,
                fallback_occasion=(
                    "current evaluation context satisfies the anchor exception"
                    if job.anchor_role == "exception"
                    else "current evaluation context"
                ),
            ),
            "trigger_condition_holds": True,
        }
        insert_at = min(1, len(items))
        items.insert(insert_at, anchor_item)
    else:
        anchor_items[0]["text"] = anchor_items[0]["text"] or str(job.constraint.get("desc", ""))
        anchor_items[0]["scope"] = anchor_scope
        anchor_items[0]["trigger_condition_holds"] = True
        anchor_items[0]["trigger_condition"] = normalize_trigger_condition(
            anchor_items[0].get("trigger_condition"),
            item_scope=anchor_scope,
            task_uid=task_uid,
            constraint_uid=constraint_uid,
            fallback_occasion=(
                "current evaluation context satisfies the anchor exception"
                if job.anchor_role == "exception"
                else "current evaluation context"
            )
        )

    items = pad_or_trim_items(items, job=job, warnings=warnings)

    seen: set[str] = set()
    for index, item in enumerate(items):
        local_id = clean_local_id(item["local_id"], f"g{index + 1}")
        if local_id in seen:
            local_id = f"{local_id}-{index + 1}"
        item["local_id"] = local_id
        seen.add(local_id)
        if item["is_anchor"]:
            item["source_constraint_uid"] = constraint_uid

    return items, warnings


MIN_GENERATED_CONSTRAINTS = 6
MAX_GENERATED_CONSTRAINTS = 7
MIN_NOISY_CONSTRAINTS = 5
MAX_NOISY_CONSTRAINTS = 6


def pad_or_trim_items(
    items: list[dict[str, Any]],
    *,
    job: ConstraintJob,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if len(items) < MIN_GENERATED_CONSTRAINTS:
        warnings.append(
            f"fewer than {MIN_GENERATED_CONSTRAINTS} constraints; padded deterministic companions"
        )
        filler = dry_run_generation(job)["generated_constraints"]
        filler_non_anchor = [item for item in filler if not item.get("is_anchor")]
        existing_texts = {str(item.get("text", "")).strip() for item in items}
        for candidate in filler_non_anchor:
            if len(items) >= MIN_GENERATED_CONSTRAINTS:
                break
            text = str(candidate.get("text", "")).strip()
            if text and text in existing_texts:
                continue
            items.append(candidate)
            existing_texts.add(text)

    if len(items) > MAX_GENERATED_CONSTRAINTS:
        warnings.append(f"more than {MAX_GENERATED_CONSTRAINTS} constraints; truncated")
        anchor = next(item for item in items if item.get("is_anchor"))
        non_anchor = [item for item in items if not item.get("is_anchor")][:MAX_NOISY_CONSTRAINTS]
        items = non_anchor[:2] + [anchor] + non_anchor[2:MAX_NOISY_CONSTRAINTS]

    noisy_count = sum(1 for item in items if not item.get("is_anchor"))
    if noisy_count < MIN_NOISY_CONSTRAINTS:
        warnings.append(f"fewer than {MIN_NOISY_CONSTRAINTS} noisy constraints after padding")
    if noisy_count > MAX_NOISY_CONSTRAINTS:
        warnings.append(f"more than {MAX_NOISY_CONSTRAINTS} noisy constraints after trimming")

    return items


def _dry_run_noisy_item(
    *,
    local_id: str,
    text: str,
    scope: ScopeName,
    task_uid: str,
    constraint_uid: str,
    occasion: str,
    holds: bool,
    except_by: str | None = None,
) -> dict[str, Any]:
    return {
        "local_id": local_id,
        "text": text,
        "scope": scope,
        "is_anchor": False,
        "except_by": except_by,
        "trigger_condition": {
            "project": task_uid if scope in {"project", "phase"} else None,
            "phase": constraint_uid if scope == "phase" else None,
            "occasion": occasion,
        },
        "trigger_condition_holds": holds,
    }


def dry_run_generation(job: ConstraintJob) -> dict[str, Any]:
    anchor_scope = anchor_scope_for_role(job.anchor_role)
    anchor_text = str(job.constraint.get("desc", "Follow the selected constraint."))
    task_uid = str(job.task.get("mac_task_uid", "project"))
    constraint_uid = str(job.constraint.get("mac_constraint_uid", "phase"))
    companion_scope: ScopeName = "phase" if anchor_scope != "phase" else "project"
    broader_scope: ScopeName = "global" if anchor_scope != "global" else "project"

    noisy_templates = [
        ("inactive_detail", f"Add supporting detail around: {anchor_text}", companion_scope, "alternate evaluation turn with additional detail requirements", False),
        ("superseded_default", f"As a broader default, use related behavior near: {anchor_text}", broader_scope, "broader default context outside the current evaluation", False),
        ("distractor_a", f"Keep a separate background constraint in the same task domain as: {anchor_text}", companion_scope, "separate background occasion outside the current evaluation context", False),
        ("distractor_b", f"Use a related historical constraint near: {anchor_text}", companion_scope, "historical context before the current evaluation turn", False),
        ("distractor_c", f"Independently keep nearby task context consistent with: {anchor_text}", "project", "separate project occasion outside the current evaluation turn", False),
    ]

    items: list[dict[str, Any]] = []
    if job.anchor_role == "exception":
        items.append(
            _dry_run_noisy_item(
                local_id="fallback",
                text=f"Generally, use the broader fallback behavior related to: {anchor_text}",
                scope="project",
                task_uid=task_uid,
                constraint_uid=constraint_uid,
                occasion="default context before the narrower exception applies",
                holds=True,
                except_by="anchor",
            )
        )

    for local_id, text, scope, occasion, holds in noisy_templates[: 5 - (1 if job.anchor_role == "exception" else 0)]:
        items.append(
            _dry_run_noisy_item(
                local_id=local_id,
                text=text,
                scope=scope,
                task_uid=task_uid,
                constraint_uid=constraint_uid,
                occasion=occasion,
                holds=holds,
            )
        )

    anchor_item = {
        "local_id": "anchor",
        "text": anchor_text,
        "scope": anchor_scope if job.anchor_role != "exception" else "phase",
        "is_anchor": True,
        "except_by": None,
        "trigger_condition": {
            "project": task_uid,
            "phase": constraint_uid,
            "occasion": (
                "current evaluation turn matches the exception condition"
                if job.anchor_role == "exception"
                else "current evaluation context"
            ),
        },
        "trigger_condition_holds": True,
    }
    insert_at = min(2, len(items))
    items.insert(insert_at, anchor_item)

    return {
        "anchor_role": job.anchor_role,
        "anchor_scope": anchor_scope,
        "generated_constraints": items[:MAX_GENERATED_CONSTRAINTS],
    }


def generation_artifact(
    *,
    job: ConstraintJob,
    generation_payload: dict[str, Any],
    generation_warnings: list[str],
    prompt: str | None,
    model: str | None,
) -> dict[str, Any]:
    task_uid = str(job.task.get("mac_task_uid", f"task-{job.task_index:05d}"))
    constraint_uid = str(
        job.constraint.get("mac_constraint_uid", f"{task_uid}-c{job.constraint_index:04d}")
    )
    try:
        items, normalization_warnings = normalize_generation(generation_payload, job=job)
        return {
            "task_uid": task_uid,
            "constraint_uid": constraint_uid,
            "constraint_text": job.constraint.get("desc"),
            "anchor_role": job.anchor_role,
            "anchor_scope": anchor_scope_for_role(job.anchor_role),
            "generated_constraints": items,
            "generation": {
                "model": model,
                "prompt_hash": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()
                if prompt is not None
                else None,
                "warnings": [*generation_warnings, *normalization_warnings],
            },
        }
    except Exception as exc:  # noqa: BLE001 - keep batch generation moving.
        return {
            "task_uid": task_uid,
            "constraint_uid": constraint_uid,
            "constraint_text": job.constraint.get("desc"),
            "anchor_role": job.anchor_role,
            "anchor_scope": anchor_scope_for_role(job.anchor_role),
            "generated_constraints": generation_payload.get("generated_constraints", []),
            "generation": {
                "model": model,
                "prompt_hash": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()
                if prompt is not None
                else None,
                "warnings": [*generation_warnings, f"generation normalization failed: {exc}"],
            },
        }


def update_task_context(context: TaskGenerationContext, artifact: dict[str, Any]) -> None:
    for item in artifact.get("generated_constraints", []):
        if not isinstance(item, dict):
            continue
        trigger = item.get("trigger_condition", {})
        if not isinstance(trigger, dict):
            trigger = {}
        text = str(item.get("text", "")).strip()
        scope = str(item.get("scope", ""))
        project = trigger.get("project")
        phase = trigger.get("phase")

        if scope == "global" and text:
            entry = {
                "local_id": item.get("local_id"),
                "text": truncate_text(text, 300),
                "is_anchor": item.get("is_anchor", False),
                "source_constraint_uid": artifact.get("constraint_uid"),
            }
            if entry not in context.global_constraints:
                context.global_constraints.append(entry)

        if isinstance(project, str) and project.strip():
            project_text = project.strip()
            if project_text not in context.introduced_projects:
                context.introduced_projects.append(project_text)

        if isinstance(phase, str) and phase.strip():
            phase_entry = {
                "project": project.strip() if isinstance(project, str) and project.strip() else None,
                "phase": phase.strip(),
            }
            if phase_entry not in context.introduced_phases:
                context.introduced_phases.append(phase_entry)


def process_job(
    job: ConstraintJob,
    args: argparse.Namespace,
    *,
    context: TaskGenerationContext | None = None,
) -> dict[str, Any]:
    print(
        f"processing constraint {job.ordinal}/{job.total} "
        f"task={job.task.get('mac_task_uid')} constraint={job.constraint.get('mac_constraint_uid')} "
        f"role={job.anchor_role}",
        flush=True,
    )
    if args.dry_run:
        return generation_artifact(
            job=job,
            generation_payload=dry_run_generation(job),
            generation_warnings=["dry-run: no LLM call was made"],
            prompt=None,
            model=None,
        )

    prompt = build_prompt(job, context=context)
    try:
        response_text = call_llm(
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            prompt=prompt,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            retries=args.retries,
            sleep=args.sleep,
        )
        payload = parse_llm_json(response_text)
        warnings: list[str] = []
    except Exception as exc:  # noqa: BLE001 - preserve failed artifact.
        payload = dry_run_generation(job)
        warnings = [f"LLM generation failed; used placeholder history: {exc}"]
    return generation_artifact(
        job=job,
        generation_payload=payload,
        generation_warnings=warnings,
        prompt=prompt,
        model=args.model,
    )


def iter_task_jobs(
    tasks: list[dict[str, Any]],
    *,
    seed: int,
    max_constraints: int | None,
    existing_artifacts: dict[str, dict[str, Any]] | None = None,
) -> list[TaskJob]:
    rng = random.Random(seed)
    weighted_roles = list(ROLE_WEIGHTS)
    weights = [ROLE_WEIGHTS[role] for role in weighted_roles]
    existing_artifacts = existing_artifacts or {}
    task_entries: list[tuple[dict[str, Any], int, list[tuple[dict[str, Any], int, AnchorRole]]]] = []
    global_constraint_count = 0
    for task_index, task in enumerate(tasks):
        constraints = task.get("constraints", [])
        if not isinstance(constraints, list):
            continue
        task_constraints: list[tuple[dict[str, Any], int, AnchorRole]] = []
        for constraint_index, constraint in enumerate(constraints):
            if not isinstance(constraint, dict):
                continue
            if not is_code_based_constraint(constraint):
                continue
            constraint_uid = str(constraint.get("mac_constraint_uid", "")).strip()
            existing = existing_artifacts.get(constraint_uid)
            existing_role = existing.get("anchor_role") if isinstance(existing, dict) else None
            if existing_role in ROLE_WEIGHTS:
                role = existing_role  # type: ignore[assignment]
            else:
                role = rng.choices(weighted_roles, weights=weights, k=1)[0]
            task_constraints.append((constraint, constraint_index, role))
            global_constraint_count += 1
            if max_constraints is not None and global_constraint_count >= max_constraints:
                break
        if task_constraints:
            task_entries.append((task, task_index, task_constraints))
        if max_constraints is not None and global_constraint_count >= max_constraints:
            break

    total_constraints = sum(len(entry[2]) for entry in task_entries)
    total_tasks = len(task_entries)
    task_jobs: list[TaskJob] = []
    ordinal = 1
    for task_ordinal, (task, task_index, task_constraints) in enumerate(task_entries, start=1):
        constraint_jobs: list[ConstraintJob] = []
        for constraint, constraint_index, role in task_constraints:
            constraint_jobs.append(
                ConstraintJob(
                    ordinal=ordinal,
                    total=total_constraints,
                    task=task,
                    task_index=task_index,
                    constraint=constraint,
                    constraint_index=constraint_index,
                    anchor_role=role,
                )
            )
            ordinal += 1
        task_jobs.append(
            TaskJob(
                ordinal=task_ordinal,
                total=total_tasks,
                task=task,
                task_index=task_index,
                constraint_jobs=constraint_jobs,
            )
        )
    return task_jobs


def process_task_job(
    task_job: TaskJob,
    args: argparse.Namespace,
    *,
    existing_artifacts: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    task_uid = task_job.task.get("mac_task_uid")
    only_uids = {str(uid).strip() for uid in (args.only_constraint or []) if str(uid).strip()}
    existing_artifacts = existing_artifacts or {}
    print(
        f"processing task {task_job.ordinal}/{task_job.total} "
        f"task={task_uid} constraints={len(task_job.constraint_jobs)}",
        flush=True,
    )
    context = TaskGenerationContext()
    artifacts: list[dict[str, Any]] = []
    for job in task_job.constraint_jobs:
        constraint_uid = str(job.constraint.get("mac_constraint_uid", "")).strip()
        if only_uids and constraint_uid not in only_uids:
            reused = existing_artifacts.get(constraint_uid)
            if reused is None:
                print(
                    f"warning: missing existing artifact for context reuse: {constraint_uid}",
                    flush=True,
                )
                continue
            artifacts.append(reused)
            update_task_context(context, reused)
            continue
        artifact = process_job(job, args, context=context)
        artifacts.append(artifact)
        update_task_context(context, artifact)
    return artifacts


def summarize_generations(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    role_counts: dict[str, int] = {}
    constraint_count_distribution: dict[str, int] = {}
    warning_count = 0
    for artifact in artifacts:
        role = str(artifact.get("anchor_role"))
        role_counts[role] = role_counts.get(role, 0) + 1
        constraints = artifact.get("generated_constraints", [])
        if isinstance(constraints, list):
            count_key = str(len(constraints))
            constraint_count_distribution[count_key] = constraint_count_distribution.get(count_key, 0) + 1
        generation = artifact.get("generation", {})
        if isinstance(generation, dict) and generation.get("warnings"):
            warning_count += 1
    return {
        "total_artifacts": len(artifacts),
        "artifacts_with_warnings": warning_count,
        "role_distribution": role_counts,
        "constraint_count_distribution": constraint_count_distribution,
    }


def main() -> int:
    load_env()
    args = parse_args()
    resolve_llm_config(args)
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    only_uids = {str(uid).strip() for uid in (args.only_constraint or []) if str(uid).strip()}
    if only_uids and not args.merge_into:
        raise ValueError("--only-constraint requires --merge-into")

    existing_payload: dict[str, Any] | None = None
    existing_histories: list[dict[str, Any]] = []
    existing_by_uid: dict[str, dict[str, Any]] = {}
    if args.merge_into:
        merge_path = resolve_path(args.merge_into)
        existing_payload = load_output_payload(merge_path)
        existing_histories = [
            artifact
            for artifact in existing_payload.get("constraint_histories", [])
            if isinstance(artifact, dict)
        ]
        existing_by_uid = artifacts_by_constraint_uid(existing_histories)

    data = load_json(input_path)
    if not isinstance(data, list):
        raise ValueError(f"Expected top-level JSON array in {input_path}")

    selected_tasks = selected_items(data, args.offset, args.limit)
    if only_uids:
        selected_tasks = tasks_with_constraints(selected_tasks, only_uids)
        if not selected_tasks:
            raise ValueError(f"No tasks matched --only-constraint uids: {sorted(only_uids)}")

    task_jobs = iter_task_jobs(
        selected_tasks,
        seed=args.seed,
        max_constraints=args.max_constraints,
        existing_artifacts=existing_by_uid or None,
    )
    workers = max(1, int(args.workers))
    artifacts: list[dict[str, Any]] = []

    if workers == 1:
        for task_job in task_jobs:
            artifacts.extend(
                process_task_job(task_job, args, existing_artifacts=existing_by_uid or None)
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    process_task_job,
                    task_job,
                    args,
                    existing_artifacts=existing_by_uid or None,
                )
                for task_job in task_jobs
            ]
            for future in as_completed(futures):
                artifacts.extend(future.result())
        artifacts.sort(key=lambda artifact: (artifact.get("task_uid", ""), artifact.get("constraint_uid", "")))

    batch_summary = summarize_generations(artifacts)
    if args.merge_into and existing_payload is not None:
        merged_histories = merge_constraint_histories(existing_histories, artifacts)
        summary = summarize_generations(merged_histories)
        payload = {
            **existing_payload,
            "source_input": str(args.input),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": bool(args.dry_run),
            "seed": args.seed,
            "summary": summary,
            "constraint_histories": merged_histories,
        }
        write_json(output_path, payload)
        print(
            f"merged {len(artifacts)} updated constraint history artifact(s) into "
            f"{len(merged_histories)} total, batch_warnings={batch_summary['artifacts_with_warnings']}, "
            f"total_warnings={summary['artifacts_with_warnings']}, output={output_path}"
        )
    else:
        payload = {
            "source_input": str(args.input),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dry_run": bool(args.dry_run),
            "seed": args.seed,
            "summary": batch_summary,
            "constraint_histories": artifacts,
        }
        write_json(output_path, payload)
        print(
            f"wrote {len(artifacts)} constraint history artifact(s), "
            f"warnings={batch_summary['artifacts_with_warnings']}, output={output_path}"
        )
    if args.dry_run:
        print("dry-run: no LLM calls were made")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
