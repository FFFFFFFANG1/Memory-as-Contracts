#!/usr/bin/env python3
"""Generate user-only MAC task histories from validated constraint sequences.

Each generated user turn is a realistic task request. Constraints are introduced
naturally in task descriptions rather than as rule reminders. The first turn for
each constraint expresses that constraint; optional carryover turns preserve the
same project/phase context without restating the constraint.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import random
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_VERSION = 1
DEFAULT_OUTPUT = Path("bench/MAC/mid_data/eval_step4_task_histories.json")

GROUNDING_SYSTEM_PROMPT = """
You ground benchmark project and phase names into stable, realistic context.

Return valid JSON only. Use the provided project and phase names exactly. Do not
invent new projects, phases, requirements, rules, or constraints. Summaries
should help another model generate realistic user task requests in the same
context without contradicting other project/phase contexts.
""".strip()

TURN_SYSTEM_PROMPT = """
You generate user-only task history turns for a benchmark.

Every output turn must be a realistic user task request. Do not generate
assistant responses. Do not write rule-reminder phrasing unless it is naturally
part of the user's task style. The first turn must naturally include the current
constraint. Later carryover turns must continue the same project/phase context
without repeating or paraphrasing the constraint.

Return valid JSON only matching the requested schema.
""".strip()

EXCEPTION_VALIDATION_SYSTEM_PROMPT = """
You judge whether a generated user turn clearly scopes an exception.

Return valid JSON only: {"passes": true|false, "reason": "short reason"}.
""".strip()

PREFERENCE_MERGE_SYSTEM_PROMPT = """
Rewrite one user task so it naturally includes a global user preference.

Return valid JSON only: {"content": "rewritten user task", "scope_expression": "short scope explanation"}.
""".strip()


@dataclass(frozen=True)
class TaskJob:
    ordinal: int
    total: int
    graph: dict[str, Any]


def load_env(env_file: Path | None = None) -> None:
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
        else:
            load_dotenv(override=False)


def load_json(path: Path, *, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return copy.deepcopy(default)
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 20)].rstrip() + "\n...[truncated]"


def empty_cache() -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "items": {},
    }


def load_cache(path: Path) -> dict[str, Any]:
    cache = load_json(path, default=empty_cache())
    if not isinstance(cache, dict):
        raise ValueError(f"Task history cache must be a JSON object: {path}")
    if cache.get("version") != CACHE_VERSION:
        raise ValueError(f"Unsupported task history cache version: {cache.get('version')}")
    if not isinstance(cache.get("items"), dict):
        cache["items"] = {}
    return cache


def cache_key(*, kind: str, model: str | None, payload: dict[str, Any]) -> str:
    material = {
        "kind": kind,
        "model": model or "",
        "payload": payload,
    }
    return sha256_text(stable_json(material))


def cache_get(cache: dict[str, Any], key: str, lock: threading.Lock) -> dict[str, Any] | None:
    with lock:
        item = cache.get("items", {}).get(key)
        if isinstance(item, dict) and isinstance(item.get("payload"), dict):
            return copy.deepcopy(item["payload"])
    return None


def cache_record(
    cache: dict[str, Any],
    key: str,
    lock: threading.Lock,
    *,
    kind: str,
    model: str | None,
    payload: dict[str, Any],
) -> None:
    with lock:
        cache.setdefault("items", {})[key] = {
            "kind": kind,
            "model": model,
            "payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        cache["updated_at"] = datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step3_base_v2.validated.json"),
        help="Validated chain-level constraint sequences.",
    )
    parser.add_argument(
        "--task-input",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step1_constraint_filtered.json"),
        help="Task dataset with prompts, task summaries, and agent names.",
    )
    parser.add_argument(
        "--fallback-task-input",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step1_focus.json"),
        help="Fallback task dataset if --task-input is missing or incomplete.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("bench/MAC/mid_data/task_hist_gen_cache.json"),
        help="Cache for project/phase grounding and constraint turn generations.",
    )
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--model", default=os.getenv("MAC_LLM_MODEL"))
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL") or os.getenv("MAC_LLM_BASE_URL"),
    )
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY"))
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-task", default=None)
    parser.add_argument("--only-task", action="append", default=[])
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--dry-run", action="store_true", help="Generate deterministic placeholders.")
    parser.add_argument(
        "--allow-placeholder",
        action="store_true",
        help="Use dry-run placeholders for failed live LLM calls.",
    )
    parser.add_argument(
        "--save-cache-every",
        type=int,
        default=10,
        help="Persist cache after this many processed tasks.",
    )
    parser.add_argument("--system-prompt-limit", type=int, default=6000)
    parser.add_argument("--style-example-limit", type=int, default=1600)
    return parser.parse_args()


def preparse_env_file() -> Path | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-file", type=Path, default=None)
    args, _ = parser.parse_known_args()
    return args.env_file


def call_llm(
    *,
    model: str,
    base_url: str | None,
    api_key: str | None,
    system_prompt: str,
    prompt: str,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> str:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise RuntimeError("openai package is required for live task history generation") from exc
    if not model:
        raise ValueError("Missing model. Pass --model or set MAC_LLM_MODEL.")
    if not api_key:
        raise ValueError("Missing API key. Pass --api-key or set OPENAI_API_KEY.")

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
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - CLI should retry provider/transport errors.
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
        return {"turns": payload}
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    return payload


def extract_graphs(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        raise ValueError("Expected input JSON object or list")
    raw = payload.get("graphs", payload.get("task_sequences", []))
    if not isinstance(raw, list):
        raise ValueError("Input must contain graphs or task_sequences list")
    return [item for item in raw if isinstance(item, dict)]


def selected_graphs(
    graphs: list[dict[str, Any]],
    *,
    offset: int,
    limit: int | None,
    start_task: str | None,
    only_task: set[str],
) -> list[dict[str, Any]]:
    selected = [
        graph
        for graph in graphs
        if not only_task or str(graph.get("task_uid", "")) in only_task
    ]
    if start_task:
        for index, graph in enumerate(selected):
            if str(graph.get("task_uid", "")) == start_task:
                selected = selected[index:]
                break
        else:
            raise ValueError(f"--start-task not found after --only-task filtering: {start_task}")
    if offset < 0:
        raise ValueError("--offset must be non-negative")
    if limit is not None and limit < 0:
        raise ValueError("--limit must be non-negative")
    selected = selected[offset:]
    if limit is not None:
        selected = selected[:limit]
    return selected


def first_message(task: dict[str, Any], role: str) -> str | None:
    messages = task.get("input", [])
    if not isinstance(messages, list):
        return None
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == role and isinstance(message.get("content"), str):
            content = message["content"].strip()
            if content:
                return content
    return None


def load_task_index(primary_path: Path, fallback_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    tasks: list[dict[str, Any]] = []
    for path in [primary_path, fallback_path]:
        try:
            payload = load_json(path)
        except FileNotFoundError:
            continue
        if isinstance(payload, list):
            tasks.extend([task for task in payload if isinstance(task, dict)])

    by_uid: dict[str, dict[str, Any]] = {}
    style_by_agent: dict[str, dict[str, str]] = {}
    for task in tasks:
        task_uid = task.get("mac_task_uid")
        if isinstance(task_uid, str) and task_uid and task_uid not in by_uid:
            by_uid[task_uid] = task
        agent_name = task.get("agent_name")
        user_content = first_message(task, "user")
        if isinstance(agent_name, str) and agent_name and user_content and agent_name not in style_by_agent:
            style_by_agent[agent_name] = {
                "source_task_uid": str(task_uid or ""),
                "content": user_content,
            }
    return by_uid, style_by_agent


def task_summary(task: dict[str, Any] | None, graph: dict[str, Any]) -> str:
    if isinstance(task, dict):
        summary = task.get("mac_task_summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    text = graph.get("constraint_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return f"Task history for {graph.get('task_uid')}"


def system_prompt(task: dict[str, Any] | None) -> str:
    if not isinstance(task, dict):
        return ""
    return first_message(task, "system") or ""


def style_example_for(
    *,
    graph: dict[str, Any],
    task: dict[str, Any] | None,
    style_by_agent: dict[str, dict[str, str]],
) -> tuple[dict[str, str], list[str]]:
    warnings: list[str] = []
    agent_name = graph.get("agent_name")
    if isinstance(agent_name, str) and agent_name in style_by_agent:
        return copy.deepcopy(style_by_agent[agent_name]), warnings
    user_content = first_message(task or {}, "user")
    if user_content:
        return {"source_task_uid": str(graph.get("task_uid", "")), "content": user_content}, warnings
    warnings.append(f"no user style example found for agent_name={agent_name!r}")
    return {"source_task_uid": "", "content": ""}, warnings


def append_actual_evaluation_turn(
    *,
    task: dict[str, Any] | None,
    output_turns: list[dict[str, Any]],
    warnings: list[str],
) -> bool:
    content = first_message(task or {}, "user")
    if not content:
        warnings.append("actual evaluation turn skipped: original user turn not found")
        return False

    output_turns.append(
        {
            "turn_index": len(output_turns),
            "role": "user",
            "kind": "actual_evaluation",
            "source_constraint_local_id": None,
            "source_constraint_uid": None,
            "scope": "actual_evaluation",
            "source_anchor_role": None,
            "content": content,
            "scope_expression": "Original AgentIF user turn used as the final evaluation task.",
            "mentions_constraint": False,
        }
    )
    return True


def extract_project_phase_spec(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    phases_by_project: dict[str, set[str]] = defaultdict(set)
    unscoped_phases: set[str] = set()
    projects: set[str] = set()

    for item in items:
        trigger = item.get("trigger_condition", {})
        if not isinstance(trigger, dict):
            continue
        project = trigger.get("project")
        phase = trigger.get("phase")
        if isinstance(project, str) and project.strip():
            project_name = project.strip()
            projects.add(project_name)
            if isinstance(phase, str) and phase.strip():
                phases_by_project[project_name].add(phase.strip())
        elif isinstance(phase, str) and phase.strip():
            unscoped_phases.add(phase.strip())

    specs: list[dict[str, Any]] = []
    for project in sorted(projects):
        specs.append(
            {
                "name": project,
                "phases": sorted(phases_by_project.get(project, set())),
            }
        )
    if unscoped_phases:
        specs.append(
            {
                "name": "__unscoped_project__",
                "phases": sorted(unscoped_phases),
            }
        )
    return specs


def dry_run_grounding(projects: list[dict[str, Any]]) -> dict[str, Any]:
    grounded_projects = []
    for project in projects:
        name = str(project.get("name", "project"))
        grounded_projects.append(
            {
                "name": name,
                "summary": f"Context for {name}: a coherent project setting used to ground related task requests.",
                "phases": [
                    {
                        "name": str(phase),
                        "summary": f"Context for phase {phase}: a specific step within {name}.",
                    }
                    for phase in project.get("phases", [])
                ],
            }
        )
    return {"projects": grounded_projects}


def validate_grounding(payload: dict[str, Any], expected_projects: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    projects = payload.get("projects")
    if not isinstance(projects, list):
        warnings.append("grounding payload missing projects list; used placeholder grounding")
        return dry_run_grounding(expected_projects), warnings

    expected_names = {str(project.get("name")) for project in expected_projects}
    expected_phases = {
        str(project.get("name")): {str(phase) for phase in project.get("phases", [])}
        for project in expected_projects
    }
    normalized: list[dict[str, Any]] = []
    seen_projects: set[str] = set()
    for project in projects:
        if not isinstance(project, dict):
            continue
        name = str(project.get("name", "")).strip()
        if not name or name not in expected_names:
            warnings.append(f"grounding ignored unexpected project {name!r}")
            continue
        seen_projects.add(name)
        summary = str(project.get("summary", "")).strip()
        phases = []
        for phase in project.get("phases", []):
            if not isinstance(phase, dict):
                continue
            phase_name = str(phase.get("name", "")).strip()
            if phase_name not in expected_phases.get(name, set()):
                warnings.append(f"grounding ignored unexpected phase {phase_name!r} for project {name!r}")
                continue
            phases.append(
                {
                    "name": phase_name,
                    "summary": str(phase.get("summary", "")).strip()
                    or f"Context for phase {phase_name}.",
                }
            )
        normalized.append(
            {
                "name": name,
                "summary": summary or f"Context for {name}.",
                "phases": phases,
            }
        )

    missing = expected_names - seen_projects
    if missing:
        warnings.append(f"grounding missing projects {sorted(missing)}; filled placeholders")
        placeholder = dry_run_grounding(
            [project for project in expected_projects if str(project.get("name")) in missing]
        )
        normalized.extend(placeholder["projects"])
    return {"projects": normalized}, warnings


def build_grounding_prompt(
    *,
    task_uid: str,
    agent_name: Any,
    task_description: str,
    projects: list[dict[str, Any]],
) -> str:
    payload = {
        "task_uid": task_uid,
        "agent_name": agent_name,
        "task_description": task_description,
        "projects_and_phases": projects,
        "output_schema": {
            "projects": [
                {
                    "name": "exact provided project name",
                    "summary": "2-3 sentence realistic project context",
                    "phases": [
                        {
                            "name": "exact provided phase name",
                            "summary": "1-2 sentence realistic phase context",
                        }
                    ],
                }
            ]
        },
        "requirements": [
            "Use provided names exactly.",
            "Do not add requirements or constraints.",
            "Summaries ground realistic future task requests.",
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def grounding_lookup(grounding: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    project_map: dict[str, dict[str, Any]] = {}
    phase_map: dict[tuple[str, str], dict[str, Any]] = {}
    for project in grounding.get("projects", []):
        if not isinstance(project, dict):
            continue
        name = str(project.get("name", "")).strip()
        if not name:
            continue
        project_map[name] = project
        for phase in project.get("phases", []):
            if not isinstance(phase, dict):
                continue
            phase_name = str(phase.get("name", "")).strip()
            if phase_name:
                phase_map[(name, phase_name)] = phase
    return project_map, phase_map


def history_class(graph: dict[str, Any]) -> str:
    if graph.get("task_level") == "hard":
        return "hard"
    count = int(graph.get("constraint_sequence_count") or len(graph.get("generated_constraints", [])))
    return "easy" if count <= 6 else "normal"


def target_turn_count(graph: dict[str, Any], *, seed: int) -> int:
    sequence_len = int(graph.get("constraint_sequence_count") or len(graph.get("generated_constraints", [])))
    klass = history_class(graph)
    rng = random.Random(f"{seed}:{graph.get('task_uid')}:target")
    if klass == "easy":
        target = 10
    elif klass == "normal":
        target = rng.randint(40, 60)
    else:
        target = rng.randint(100, 150)
    return max(sequence_len, target)


def turn_allocations(items: list[dict[str, Any]], *, target: int, seed: int, task_uid: str) -> dict[str, int]:
    local_ids = [str(item.get("local_id")) for item in items if item.get("local_id")]
    if not local_ids:
        return {}
    allocations = {local_id: 1 for local_id in local_ids}
    extra = max(0, target - len(local_ids))
    rng = random.Random(f"{seed}:{task_uid}:allocations")
    for _ in range(extra):
        allocations[rng.choice(local_ids)] += 1
    return allocations


# Generation prompts.

def source_system_prompt_for_turn(scope: str) -> str:
    if scope == "global":
        return (
            "The task must make the global applicability clear without sounding like a direct rule reminder. "
            "Use natural user wording for constraints that apply to all agent actions, such as "
            "'always remember that...', 'for everything you do here...', or 'from now on in this chat...', "
            "then embed the requirement in the task."
        )
    if scope == "project":
        return (
            "The task must make the project context unambiguous. Use natural user wording such as "
            "'for this project...', 'throughout this report...', or 'while working on this message...', "
            "then embed the requirement in the project-specific task. The introduce turn must mention the "
            "exact provided project name."
        )
    if scope == "phase":
        return (
            "The task must make both project and phase context unambiguous. Here, phase means a bounded "
            "part of a project; it may be temporal, semantic, structural, or functional, such as a phase, "
            "section, component, module, workflow step, addendum, or subsection. Use natural user wording "
            "such as 'for this section of the project...', 'within the safety-triage component...', "
            "'in the report addendum...', or 'for this module...', then embed the requirement in that "
            "project part's task. The introduce turn must mention the exact provided project name and exact "
            "provided phase name."
        )
    return "The task must make the exception occasion or special-case context unambiguous."


def build_turn_prompt(
    *,
    graph: dict[str, Any],
    task: dict[str, Any] | None,
    item: dict[str, Any],
    turn_count: int,
    task_description: str,
    style_example: dict[str, str],
    grounding: dict[str, Any],
    args: argparse.Namespace,
) -> str:
    trigger = item.get("trigger_condition", {})
    if not isinstance(trigger, dict):
        trigger = {}
    scope = str(item.get("scope", ""))
    project = trigger.get("project")
    phase = trigger.get("phase")
    project_map, phase_map = grounding_lookup(grounding)
    project_summary = ""
    phase_summary = ""
    if isinstance(project, str):
        project_summary = str(project_map.get(project, {}).get("summary", ""))
    if isinstance(project, str) and isinstance(phase, str):
        phase_summary = str(phase_map.get((project, phase), {}).get("summary", ""))

    variable_annotations = {
        "project_context": "The concrete project setting for this task. Use the project name or a clear grounded description when scope is project or phase.",
        "phase_context": "A bounded part of the project. It may be temporal, semantic, structural, or functional, such as a phase, section, component, module, workflow step, addendum, or subsection. Use this when scope is phase.",
        "deliverable_request": "The realistic work the user asks the agent to perform in this turn.",
        "constraint_requirement": "The current constraint that must be naturally included only in the introduce turn.",
        "occasion": "The scenario or condition that makes this task request relevant, especially for global or exception constraints.",
    }
    payload = {
        "task_uid": graph.get("task_uid"),
        "agent_name": graph.get("agent_name"),
        "task_description": task_description,
        "system_prompt": truncate_text(system_prompt(task), args.system_prompt_limit),
        "style_example_user_turn": truncate_text(style_example.get("content", ""), args.style_example_limit),
        "input_variable_annotations": variable_annotations,
        "scope_definitions": {
            "global": "A constraint that applies to all relevant agent actions in the chat or task context.",
            "project": "A named project or workstream. Project-scoped introduce turns must include the exact project name.",
            "phase": (
                "A bounded part of a project. It may be temporal, semantic, structural, or functional, "
                "such as a phase, section, component, module, workflow step, addendum, turn, file, or subsection. "
                "Phase-scoped introduce turns must include the exact project name and exact phase name."
            ),
            "exception": "A specific occasion or special-case context where a constraint applies or is overridden.",
        },
        "required_exact_scope_mentions": {
            "project_name": project if scope in {"project", "phase"} and isinstance(project, str) else None,
            "phase_name": phase if scope == "phase" and isinstance(phase, str) else None,
            "occasion": trigger.get("occasion") if item.get("source_anchor_role") == "exception" else None,
        },
        "current_constraint": {
            "local_id": item.get("local_id"),
            "text": item.get("text"),
            "scope": scope,
            "is_anchor": item.get("is_anchor"),
            "source_constraint_uid": item.get("source_constraint_uid"),
            "source_anchor_role": item.get("source_anchor_role"),
            "trigger_condition": trigger,
            "trigger_condition_holds": item.get("trigger_condition_holds"),
        },
        "grounding": {
            "all_projects_and_phases": grounding,
            "project_summary": project_summary,
            "phase_summary": phase_summary,
        },
        "requested_turn_count": turn_count,
        "scope_requirement": source_system_prompt_for_turn(scope),
        "output_schema": {
            "turns": [
                {
                    "kind": "introduce",
                    "content": "realistic user task that naturally includes the constraint",
                    "scope_expression": "brief explanation of how scope is unambiguous",
                    "mentions_constraint": True,
                },
                {
                    "kind": "carryover",
                    "content": "realistic follow-up task in the same context without restating the constraint",
                    "scope_expression": "brief explanation of how context is preserved",
                    "mentions_constraint": False,
                },
            ]
        },
        "requirements": [
            "Return exactly requested_turn_count turns.",
            "Return exactly one introduce turn, and it must be first.",
            "Generate user turns only; no assistant responses.",
            "Every turn must be a realistic task request in the style of the example.",
            "The introduce turn must naturally include the current constraint requirement.",
            "Carryover turns must not repeat or paraphrase the current constraint requirement.",
            "Do not change the provided project or phase ground truth.",
            "Make scope unambiguous in the task text.",
            "If required_exact_scope_mentions.project_name is not null, the introduce turn content or scope_expression must include that exact project name.",
            "If required_exact_scope_mentions.phase_name is not null, the introduce turn content or scope_expression must include that exact phase name.",
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


# Deterministic placeholder generation.

def dry_run_turns(item: dict[str, Any], turn_count: int, grounding: dict[str, Any]) -> dict[str, Any]:
    trigger = item.get("trigger_condition", {})
    if not isinstance(trigger, dict):
        trigger = {}
    project = trigger.get("project") or "the current project"
    phase = trigger.get("phase") or "the current phase"
    occasion = trigger.get("occasion") or "the relevant scenario"
    scope = item.get("scope")
    if item.get("source_anchor_role") == "exception":
        prefix = (
            f"For {occasion} in project {project} during {phase}, "
            "prepare a realistic exception-case task request that includes this requirement"
        )
    else:
        prefix = {
            "global": f"For {occasion}, prepare a realistic task request that includes this requirement",
            "project": f"For project {project}, prepare a realistic task request that includes this requirement",
            "phase": f"For project {project} during {phase}, prepare a realistic task request that includes this requirement",
        }.get(str(scope), f"For {occasion}, prepare a special-case task request that includes this requirement")
    turns = [
        {
            "kind": "introduce",
            "content": f"{prefix}: {item.get('text')}",
            "scope_expression": str(scope),
            "mentions_constraint": True,
        }
    ]
    for index in range(1, turn_count):
        turns.append(
            {
                "kind": "carryover",
                "content": f"Continue the work in {project} / {phase} with a related follow-up task #{index}.",
                "scope_expression": f"continues {project} / {phase}",
                "mentions_constraint": False,
            }
        )
    return {"turns": turns}


# Deterministic turn validation.

def validate_turn_payload(payload: dict[str, Any], *, item: dict[str, Any], expected_count: int) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list):
        return [], ["turn payload missing turns list"]
    if len(raw_turns) != expected_count:
        errors.append(f"expected {expected_count} turns, got {len(raw_turns)}")

    turns: list[dict[str, Any]] = []
    introduce_count = 0
    for index, raw in enumerate(raw_turns):
        if not isinstance(raw, dict):
            errors.append(f"turn {index} is not an object")
            continue
        kind = str(raw.get("kind", "")).strip()
        content = str(raw.get("content", "")).strip()
        mentions = raw.get("mentions_constraint")
        if kind not in {"introduce", "carryover"}:
            errors.append(f"turn {index} has invalid kind {kind!r}")
        if not content:
            errors.append(f"turn {index} has empty content")
        if kind == "introduce":
            introduce_count += 1
            if mentions is not True:
                errors.append("introduce turn must have mentions_constraint=true")
        if kind == "carryover" and mentions is not False:
            errors.append(f"carryover turn {index} must have mentions_constraint=false")
        turns.append(
            {
                "kind": kind or ("introduce" if index == 0 else "carryover"),
                "content": content,
                "scope_expression": str(raw.get("scope_expression", "")).strip(),
                "mentions_constraint": bool(mentions),
            }
        )
    if introduce_count != 1:
        errors.append(f"expected exactly one introduce turn, got {introduce_count}")
    elif turns and turns[0]["kind"] != "introduce":
        errors.append("introduce turn must be first")

    scope = item.get("scope")
    trigger = item.get("trigger_condition", {})
    if not isinstance(trigger, dict):
        trigger = {}
    introduce_content = turns[0]["content"] if turns else ""
    introduce_scope_expression = turns[0]["scope_expression"] if turns else ""
    introduce_scope_text = f"{introduce_content}\n{introduce_scope_expression}"
    if scope == "project":
        project = trigger.get("project")
        if isinstance(project, str) and project.strip() and project.strip() not in introduce_scope_text:
            errors.append("project-scope introduce turn does not include the project name")
    if scope == "phase":
        phase = trigger.get("phase")
        if isinstance(phase, str) and phase.strip() and phase.strip() not in introduce_scope_text:
            errors.append("phase-scope introduce turn does not include the phase name")
    return turns, errors


# LLM validation for semantic exception scope.

def validate_exception_context_with_llm(
    *,
    item: dict[str, Any],
    turns: list[dict[str, Any]],
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> list[str]:
    if item.get("source_anchor_role") != "exception" or not turns or args.dry_run:
        return []

    trigger = item.get("trigger_condition", {})
    if not isinstance(trigger, dict):
        trigger = {}
    occasion = trigger.get("occasion")
    if not isinstance(occasion, str) or not occasion.strip():
        return []

    introduce = turns[0]
    prompt_payload = {
        "constraint_local_id": item.get("local_id"),
        "constraint_hash": sha256_text(stable_json(item)),
        "occasion": occasion.strip(),
        "project": trigger.get("project"),
        "phase": trigger.get("phase"),
        "content_hash": sha256_text(str(introduce.get("content", ""))),
        "scope_expression_hash": sha256_text(str(introduce.get("scope_expression", ""))),
    }
    key = cache_key(kind="exception_validation", model=args.model, payload=prompt_payload)
    cached = cache_get(cache, key, cache_lock)
    if cached:
        passes = cached.get("passes") is True
        reason = str(cached.get("reason", "")).strip()
        return [] if passes else [f"exception introduce turn does not precisely state exception scenario/effective timing: {reason}"]

    prompt = json.dumps(
        {
            "exception_occasion": occasion.strip(),
            "project": trigger.get("project"),
            "phase": trigger.get("phase"),
            "constraint": item.get("text"),
            "introduce_turn": introduce.get("content", ""),
            "scope_expression": introduce.get("scope_expression", ""),
            "judge": (
                "Does the introduce turn precisely state the exception scenario and when it applies? "
                "Accept natural paraphrases. Reject if the occasion or effective timing is missing or ambiguous."
            ),
        },
        indent=2,
        ensure_ascii=False,
    )
    raw = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=EXCEPTION_VALIDATION_SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=min(args.max_tokens, 512),
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = parse_llm_json(raw)
    passes = payload.get("passes") is True
    reason = str(payload.get("reason", "")).strip()[:300]
    result = {"passes": passes, "reason": reason}
    cache_record(cache, key, cache_lock, kind="exception_validation", model=args.model, payload=result)
    return [] if passes else [f"exception introduce turn does not precisely state exception scenario/effective timing: {reason}"]


# Preference merge finalization.

def split_preference_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    constraints: list[dict[str, Any]] = []
    preferences: list[dict[str, Any]] = []
    for item in items:
        if item.get("is_preference") is True or item.get("source_anchor_role") == "preference":
            preferences.append(item)
        else:
            constraints.append(item)
    return constraints, preferences


def preference_merge_targets(output_turns: list[dict[str, Any]]) -> list[int]:
    return [
        index
        for index, turn in enumerate(output_turns)
        if turn.get("kind") == "introduce" and turn.get("scope") == "global"
    ]


def merge_preference_into_turn(
    *,
    task_uid: str,
    preference: dict[str, Any],
    turn: dict[str, Any],
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> dict[str, str]:
    preference_text = str(preference.get("text", "")).strip()
    if not preference_text:
        return {
            "content": str(turn.get("content", "")),
            "scope_expression": str(turn.get("scope_expression", "")),
        }

    prompt_payload = {
        "task_uid": task_uid,
        "preference_local_id": preference.get("local_id"),
        "preference_hash": sha256_text(stable_json(preference)),
        "turn_content_hash": sha256_text(str(turn.get("content", ""))),
        "turn_scope_expression_hash": sha256_text(str(turn.get("scope_expression", ""))),
    }
    key = cache_key(kind="preference_merge", model=args.model, payload=prompt_payload)
    cached = None if args.dry_run else cache_get(cache, key, cache_lock)
    if cached:
        return {
            "content": str(cached.get("content", turn.get("content", ""))).strip(),
            "scope_expression": str(cached.get("scope_expression", turn.get("scope_expression", ""))).strip(),
        }

    if args.dry_run:
        return {
            "content": f"{turn.get('content', '')}\n\nAlso, as a preference for this task history: {preference_text}",
            "scope_expression": f"{turn.get('scope_expression', '')} The task also introduces a global preference.",
        }

    prompt = json.dumps(
        {
            "current_user_turn": turn.get("content", ""),
            "current_scope_expression": turn.get("scope_expression", ""),
            "preference": preference_text,
            "requirements": [
                "Rewrite the current user turn as one realistic user task.",
                "Naturally include the preference as a global preference for future work in this task/chat.",
                "Preserve all existing task details and existing constraint requirements.",
                "Do not add assistant output.",
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
    raw = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=PREFERENCE_MERGE_SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = parse_llm_json(raw)
    content = str(payload.get("content", "")).strip()
    scope_expression = str(payload.get("scope_expression", "")).strip()
    if not content:
        raise ValueError("preference merge returned empty content")
    if preference_text not in content and not args.dry_run:
        # Keep this deterministic check strict: the generated preference text is short and should survive rewriting.
        content = f"{content}\n\nFor everything we do here, please also remember this preference: {preference_text}"
    if not scope_expression:
        scope_expression = str(turn.get("scope_expression", "")).strip()
    result = {"content": content, "scope_expression": scope_expression}
    cache_record(cache, key, cache_lock, kind="preference_merge", model=args.model, payload=result)
    return result


def apply_preference_merges(
    *,
    task_uid: str,
    preferences: list[dict[str, Any]],
    output_turns: list[dict[str, Any]],
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    merge_records: list[dict[str, Any]] = []
    if not preferences:
        return merge_records, warnings, errors

    targets = preference_merge_targets(output_turns)
    if not targets:
        warnings.append("preference merge skipped: no global introduce turn available")
        return merge_records, warnings, errors

    rng = random.Random(f"{args.seed}:{task_uid}:preference_merge")
    for preference in preferences:
        target_index = rng.choice(targets)
        target_turn = output_turns[target_index]
        try:
            merged = merge_preference_into_turn(
                task_uid=task_uid,
                preference=preference,
                turn=target_turn,
                args=args,
                cache=cache,
                cache_lock=cache_lock,
            )
            target_turn["content"] = merged["content"]
            target_turn["scope_expression"] = merged["scope_expression"]
            target_turn.setdefault("merged_preferences", []).append(preference.get("local_id"))
            merge_records.append(
                {
                    "preference_local_id": preference.get("local_id"),
                    "source_constraint_uid": preference.get("source_constraint_uid"),
                    "target_turn_index": target_turn.get("turn_index"),
                    "target_constraint_local_id": target_turn.get("source_constraint_local_id"),
                }
            )
        except Exception as exc:  # noqa: BLE001 - preserve task artifact and continue.
            errors.append(f"{preference.get('local_id')}: preference merge failed: {exc}")
    return merge_records, warnings, errors


# Generation and repair loop.

def live_or_cached_grounding(
    *,
    graph: dict[str, Any],
    task_description: str,
    projects: list[dict[str, Any]],
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> tuple[dict[str, Any], str, list[str]]:
    key_payload = {
        "task_uid": graph.get("task_uid"),
        "agent_name": graph.get("agent_name"),
        "task_description": task_description,
        "projects": projects,
    }
    key = cache_key(kind="grounding", model=args.model, payload=key_payload)
    cached = None if args.dry_run else cache_get(cache, key, cache_lock)
    if cached:
        grounding, warnings = validate_grounding(cached, projects)
        return grounding, "hit", warnings
    if args.dry_run or not projects:
        return dry_run_grounding(projects), "dry_run", []

    prompt = build_grounding_prompt(
        task_uid=str(graph.get("task_uid")),
        agent_name=graph.get("agent_name"),
        task_description=task_description,
        projects=projects,
    )
    raw = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=GROUNDING_SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = parse_llm_json(raw)
    grounding, warnings = validate_grounding(payload, projects)
    cache_record(cache, key, cache_lock, kind="grounding", model=args.model, payload=grounding)
    return grounding, "miss", warnings


def live_or_cached_turns(
    *,
    graph: dict[str, Any],
    task: dict[str, Any] | None,
    item: dict[str, Any],
    turn_count: int,
    task_description: str,
    style_example: dict[str, str],
    grounding: dict[str, Any],
    args: argparse.Namespace,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> tuple[list[dict[str, Any]], str, list[str], list[str]]:
    prompt_payload = {
        "task_uid": graph.get("task_uid"),
        "constraint_local_id": item.get("local_id"),
        "constraint_hash": sha256_text(stable_json(item)),
        "turn_count": turn_count,
        "task_description": task_description,
        "style_example_hash": sha256_text(style_example.get("content", "")),
        "grounding_hash": sha256_text(stable_json(grounding)),
    }
    key = cache_key(kind="turns", model=args.model, payload=prompt_payload)
    cached = None if args.dry_run else cache_get(cache, key, cache_lock)
    if cached:
        turns, errors = validate_turn_payload(cached, item=item, expected_count=turn_count)
        if not errors:
            errors.extend(
                validate_exception_context_with_llm(
                    item=item,
                    turns=turns,
                    args=args,
                    cache=cache,
                    cache_lock=cache_lock,
                )
            )
        return turns, "hit", [], errors

    if args.dry_run:
        payload = dry_run_turns(item, turn_count, grounding)
        turns, errors = validate_turn_payload(payload, item=item, expected_count=turn_count)
        return turns, "dry_run", [], errors

    prompt = build_turn_prompt(
        graph=graph,
        task=task,
        item=item,
        turn_count=turn_count,
        task_description=task_description,
        style_example=style_example,
        grounding=grounding,
        args=args,
    )
    raw = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        system_prompt=TURN_SYSTEM_PROMPT,
        prompt=prompt,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = parse_llm_json(raw)
    turns, errors = validate_turn_payload(payload, item=item, expected_count=turn_count)
    if not errors:
        errors.extend(
            validate_exception_context_with_llm(
                item=item,
                turns=turns,
                args=args,
                cache=cache,
                cache_lock=cache_lock,
            )
        )
    if not errors:
        cache_record(cache, key, cache_lock, kind="turns", model=args.model, payload=payload)
    return turns, "miss", [], errors


def process_task(
    job: TaskJob,
    *,
    args: argparse.Namespace,
    task_by_uid: dict[str, dict[str, Any]],
    style_by_agent: dict[str, dict[str, str]],
    cache: dict[str, Any],
    cache_lock: threading.Lock,
) -> dict[str, Any]:
    graph = job.graph
    task_uid = str(graph.get("task_uid", ""))
    print(f"generating task history {job.ordinal}/{job.total} task={task_uid}", flush=True)
    task = task_by_uid.get(task_uid)
    all_items = [item for item in graph.get("generated_constraints", []) if isinstance(item, dict)]
    items, preferences = split_preference_items(all_items)
    warnings: list[str] = []
    errors: list[str] = []

    style_example, style_warnings = style_example_for(
        graph=graph,
        task=task,
        style_by_agent=style_by_agent,
    )
    warnings.extend(style_warnings)
    description = task_summary(task, graph)
    projects = extract_project_phase_spec(items)

    try:
        grounding, grounding_cache, grounding_warnings = live_or_cached_grounding(
            graph=graph,
            task_description=description,
            projects=projects,
            args=args,
            cache=cache,
            cache_lock=cache_lock,
        )
        warnings.extend(grounding_warnings)
    except Exception as exc:  # noqa: BLE001 - task artifact should preserve failure.
        if not args.allow_placeholder:
            grounding = dry_run_grounding(projects)
            grounding_cache = "failed"
            errors.append(f"grounding generation failed: {exc}")
        else:
            grounding = dry_run_grounding(projects)
            grounding_cache = "placeholder"
            warnings.append(f"grounding generation failed; used placeholder: {exc}")

    target = target_turn_count(graph, seed=args.seed)
    allocations = turn_allocations(items, target=target, seed=args.seed, task_uid=task_uid)
    output_turns: list[dict[str, Any]] = []
    constraint_generations: list[dict[str, Any]] = []
    cache_counts = Counter()

    for item in items:
        local_id = str(item.get("local_id", ""))
        turn_count = allocations.get(local_id, 1)
        try:
            turns, cache_status, turn_warnings, turn_errors = live_or_cached_turns(
                graph=graph,
                task=task,
                item=item,
                turn_count=turn_count,
                task_description=description,
                style_example=style_example,
                grounding=grounding,
                args=args,
                cache=cache,
                cache_lock=cache_lock,
            )
            warnings.extend(turn_warnings)
            if turn_errors and args.allow_placeholder:
                placeholder = dry_run_turns(item, turn_count, grounding)
                turns, placeholder_errors = validate_turn_payload(
                    placeholder,
                    item=item,
                    expected_count=turn_count,
                )
                turn_errors = placeholder_errors
                cache_status = "placeholder"
                warnings.append(f"turn validation failed for {local_id}; used placeholder")
            errors.extend([f"{local_id}: {error}" for error in turn_errors])
        except Exception as exc:  # noqa: BLE001 - preserve failed constraint.
            if not args.allow_placeholder:
                turns = []
                cache_status = "failed"
                errors.append(f"{local_id}: turn generation failed: {exc}")
            else:
                placeholder = dry_run_turns(item, turn_count, grounding)
                turns, placeholder_errors = validate_turn_payload(
                    placeholder,
                    item=item,
                    expected_count=turn_count,
                )
                cache_status = "placeholder"
                warnings.append(f"{local_id}: turn generation failed; used placeholder: {exc}")
                errors.extend([f"{local_id}: {error}" for error in placeholder_errors])

        cache_counts[cache_status] += 1
        constraint_generations.append(
            {
                "local_id": local_id,
                "planned_turn_count": turn_count,
                "actual_turn_count": len(turns),
                "cache": cache_status,
            }
        )
        for turn in turns:
            output_turns.append(
                {
                    "turn_index": len(output_turns),
                    "role": "user",
                    "kind": turn.get("kind"),
                    "source_constraint_local_id": local_id,
                    "source_constraint_uid": item.get("source_constraint_uid"),
                    "scope": item.get("scope"),
                    "source_anchor_role": item.get("source_anchor_role"),
                    "content": turn.get("content", ""),
                    "scope_expression": turn.get("scope_expression", ""),
                    "mentions_constraint": turn.get("mentions_constraint"),
                }
            )

    preference_merges, preference_warnings, preference_errors = apply_preference_merges(
        task_uid=task_uid,
        preferences=preferences,
        output_turns=output_turns,
        args=args,
        cache=cache,
        cache_lock=cache_lock,
    )
    warnings.extend(preference_warnings)
    errors.extend(preference_errors)

    history_user_turn_count = len(output_turns)
    klass = history_class(graph)
    if history_user_turn_count != target and not errors:
        errors.append(
            f"history_user_turn_count {history_user_turn_count} != target_history_turn_count {target}"
        )

    has_actual_evaluation = append_actual_evaluation_turn(
        task=task,
        output_turns=output_turns,
        warnings=warnings,
    )

    return {
        "task_uid": task_uid,
        "agent_name": graph.get("agent_name"),
        "task_level": klass,
        "source_task_level": graph.get("task_level"),
        "source_graph_count": graph.get("source_graph_count"),
        "constraint_sequence_count": len(items),
        "preference_count": len(preferences),
        "target_history_turn_count": target,
        "history_user_turn_count": history_user_turn_count,
        "evaluation_user_turn_count": 1 if has_actual_evaluation else 0,
        "target_user_turn_count": target + 1,
        "actual_user_turn_count": len(output_turns),
        "style_example": {
            "source_task_uid": style_example.get("source_task_uid", ""),
            "content": truncate_text(style_example.get("content", ""), 2000),
        },
        "project_phase_grounding": grounding,
        "turns": output_turns,
        "generation": {
            "model": None if args.dry_run else args.model,
            "grounding_cache": grounding_cache,
            "constraint_generation_cache": dict(cache_counts),
            "constraint_generations": constraint_generations,
            "preference_merges": preference_merges,
            "warnings": warnings,
            "errors": errors,
        },
    }


def iter_jobs(graphs: list[dict[str, Any]]) -> list[TaskJob]:
    total = len(graphs)
    return [
        TaskJob(ordinal=index, total=total, graph=graph)
        for index, graph in enumerate(graphs, start=1)
    ]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    class_counts = Counter(result.get("task_level") for result in results)
    length_counts = Counter(str(result.get("actual_user_turn_count")) for result in results)
    failed_tasks = [
        result.get("task_uid")
        for result in results
        if result.get("generation", {}).get("errors")
    ]
    cache_counts = Counter()
    for result in results:
        generation = result.get("generation", {})
        if isinstance(generation, dict):
            cache_counts[str(generation.get("grounding_cache"))] += 1
            for key, value in generation.get("constraint_generation_cache", {}).items():
                cache_counts[f"turns_{key}"] += int(value)
    return {
        "total_tasks": len(results),
        "task_class_distribution": dict(class_counts),
        "total_user_turns": sum(int(result.get("actual_user_turn_count", 0)) for result in results),
        "failed_tasks": len(failed_tasks),
        "failed_task_uids": failed_tasks[:50],
        "history_length_distribution": dict(sorted(length_counts.items(), key=lambda item: int(item[0]))),
        "cache_distribution": dict(cache_counts),
    }


def main() -> int:
    load_env(preparse_env_file())
    args = parse_args()
    input_path = resolve_path(args.input)
    task_input_path = resolve_path(args.task_input)
    fallback_task_input_path = resolve_path(args.fallback_task_input)
    output_path = resolve_path(args.output)
    cache_path = resolve_path(args.cache)

    graphs = selected_graphs(
        extract_graphs(load_json(input_path)),
        offset=args.offset,
        limit=args.limit,
        start_task=args.start_task,
        only_task={str(uid) for uid in args.only_task},
    )
    task_by_uid, style_by_agent = load_task_index(task_input_path, fallback_task_input_path)
    cache = load_cache(cache_path)
    cache_lock = threading.Lock()
    jobs = iter_jobs(graphs)
    workers = max(1, int(args.workers))
    results: list[dict[str, Any]] = []

    if workers == 1:
        for completed, job in enumerate(jobs, start=1):
            results.append(
                process_task(
                    job,
                    args=args,
                    task_by_uid=task_by_uid,
                    style_by_agent=style_by_agent,
                    cache=cache,
                    cache_lock=cache_lock,
                )
            )
            if args.save_cache_every and completed % args.save_cache_every == 0:
                with cache_lock:
                    write_json(cache_path, cache)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    process_task,
                    job,
                    args=args,
                    task_by_uid=task_by_uid,
                    style_by_agent=style_by_agent,
                    cache=cache,
                    cache_lock=cache_lock,
                )
                for job in jobs
            ]
            for completed, future in enumerate(as_completed(futures), start=1):
                results.append(future.result())
                if args.save_cache_every and completed % args.save_cache_every == 0:
                    with cache_lock:
                        write_json(cache_path, cache)
        results.sort(key=lambda result: str(result.get("task_uid", "")))

    with cache_lock:
        write_json(cache_path, cache)
    summary = summarize(results)
    payload = {
        "source_input": str(args.input),
        "task_input": str(args.task_input),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": bool(args.dry_run),
        "summary": summary,
        "task_histories": results,
    }
    write_json(output_path, payload)
    print(
        f"wrote {len(results)} task history artifact(s), "
        f"user_turns={summary['total_user_turns']}, failed={summary['failed_tasks']}, "
        f"output={output_path}"
    )
    return 0 if summary["failed_tasks"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
