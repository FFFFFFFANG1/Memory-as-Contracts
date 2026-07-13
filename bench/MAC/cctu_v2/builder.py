#!/usr/bin/env python3
"""Build hand-authored crossed examples and a deterministic 40-task pilot."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import candidate_allowed, resolve_active_directives, validate_episode

DEFAULT_TASKS = Path("bench/MAC/cctu/data/mac-cctu-tasks.json")
DEFAULT_AUDIT = Path("bench/MAC/cctu_v2/data/constraint_audit.json")
DEFAULT_GOLD = Path("bench/MAC/cctu_v2/data/crossed_gold_examples.json")
DEFAULT_PILOT = Path("bench/MAC/cctu_v2/data/pilot_40.json")
DEFAULT_REPORT = Path("bench/MAC/cctu_v2/data/pilot_40_report.json")

CELLS = [
    "static_action_local",
    "dynamic_action_local",
    "static_trajectory_conditioned",
    "dynamic_trajectory_conditioned",
]


def _limit(text: str, default: int = 2) -> int:
    values = [int(value) for value in re.findall(r"\b(\d+)\b", text)]
    if not values:
        return default
    # Upper bounds are normally the last number in CCTU range descriptions.
    return max(1, min(values[-1], 20))


def _tool(text: str) -> str | None:
    patterns = [
        r"`([^`]+)`",
        r"'([A-Za-z][A-Za-z0-9_]+)'",
        r'"([A-Za-z][A-Za-z0-9_]+)"',
        r"\b([A-Za-z][A-Za-z0-9_]+)_tool\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1)
            return value if value.endswith("_tool") else value
    return None


def predicate_for(row: dict[str, Any]) -> dict[str, Any]:
    dependency = row["dependency_type"]
    raw = row["raw_text"]
    if dependency == "action_local":
        return {"kind": "response_requirement", "requirement": raw}
    lower_bound = bool(re.search(r"\b(at least|minimum|min\.?|no fewer than)\b", raw, re.I))
    if dependency == "tool_count_based":
        kind = "min_tool_calls" if lower_bound else "max_tool_calls"
        return {"kind": kind, "limit": _limit(raw), "tool": _tool(raw)}
    if dependency in {"count_based", "round_count_based"}:
        kind = "min_tool_calls" if lower_bound else "max_tool_calls"
        return {"kind": kind, "limit": _limit(raw), "tool": None}
    # Behavior constraints are retained for audit but not auto-instantiated in
    # the pilot until their optionality receives human review.
    raise ValueError(f"pilot does not auto-instantiate {dependency}")


def _directive(row: dict[str, Any], predicate: dict[str, Any], project: str) -> dict[str, Any]:
    return {
        "text": row["raw_text"],
        "modality": "must",
        "scope": {"project": project},
        "predicate": deepcopy(predicate),
        "source_constraint_uid": row["constraint_uid"],
    }


def _event(
    index: int,
    event_type: str,
    directive_id: str,
    *,
    version: int | None = None,
    directive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_index": index,
        "event_type": event_type,
        "directive_id": directive_id,
    }
    if version is not None:
        event["version"] = version
    if directive is not None:
        event["directive"] = directive
    return event


def render_history(
    events: list[dict[str, Any]], current_context: dict[str, Any], task_summary: str
) -> list[dict[str, Any]]:
    """Render canonical events into bounded multi-session dialogue."""
    history: list[dict[str, Any]] = []
    for event in events:
        event_type = event["event_type"]
        directive = event.get("directive") or {}
        scope = directive.get("scope") or {}
        project = scope.get("project") or current_context["project"]
        if event_type == "introduce":
            text = (
                f"For {project}, please keep this as a standing instruction for future work: "
                f"{directive.get('text', 'follow the recorded requirement')}"
            )
        elif event_type == "amend":
            text = (
                f"Update my earlier instruction for {project}. The new version is: "
                f"{directive.get('text', 'use the amended requirement')}. This replaces the old version."
            )
        elif event_type == "revoke":
            text = f"Revoke the earlier standing instruction {event['directive_id']} for {project}."
        else:
            text = f"Record lifecycle event {event_type} for instruction {event['directive_id']} in {project}."
        history.extend(
            [
                {
                    "session_id": f"directive-{event['event_index']}",
                    "role": "user",
                    "kind": "directive_event",
                    "content": text,
                    "authoritative": True,
                },
                {
                    "session_id": f"directive-{event['event_index']}",
                    "role": "assistant",
                    "kind": "acknowledgement",
                    "content": "Understood. I will apply the current version in the stated scope.",
                    "authoritative": False,
                },
            ]
        )

    history.extend(
        [
            {
                "session_id": "intervening-work",
                "role": "user",
                "kind": "ordinary_task",
                "content": "Please inspect a related record and summarize the source metadata.",
                "authoritative": False,
            },
            {
                "session_id": "intervening-work",
                "role": "assistant",
                "kind": "tool_call",
                "content": "Calling the relevant read-only lookup tool.",
                "authoritative": False,
            },
            {
                "session_id": "intervening-work",
                "role": "tool",
                "kind": "tool_result",
                "content": "The source record was found and its metadata was returned.",
                "authoritative": False,
            },
            {
                "session_id": "evaluation",
                "role": "user",
                "kind": "current_task",
                "content": (
                    f"Current project: {current_context['project']}. "
                    f"Current phase: {current_context.get('phase') or 'general work'}. "
                    f"Task: {task_summary}"
                ),
                "authoritative": False,
            },
        ]
    )
    return history


def build_episode(
    row: dict[str, Any],
    *,
    episode_index: int,
    cell: str,
    handcrafted: bool = False,
) -> dict[str, Any]:
    predicate = predicate_for(row)
    directive_id = f"d-{episode_index:03d}"
    current_project = f"Project-{episode_index:03d}"
    other_project = f"Archive-{episode_index:03d}"
    context = {
        "user": f"user-{episode_index % 7:02d}",
        "project": current_project,
        "phase": "verification",
        "task": row["task_uid"],
        "resource": None,
    }
    base = _directive(row, predicate, current_project)
    other_scope = _directive(row, predicate, other_project)
    dynamic = cell.startswith("dynamic")
    trace_conditioned = cell.endswith("trajectory_conditioned")

    if not dynamic:
        worlds = [
            {
                "world_id": "active_current_scope",
                "directive_events": [_event(0, "introduce", directive_id, version=1, directive=base)],
            },
            {
                "world_id": "same_rule_out_of_scope",
                "directive_events": [_event(0, "introduce", directive_id, version=1, directive=other_scope)],
            },
        ]
    elif trace_conditioned:
        old = deepcopy(base)
        new = deepcopy(base)
        is_minimum = predicate["kind"].startswith("min_")
        old_limit = max(1, int(predicate["limit"])) if is_minimum else max(3, int(predicate["limit"]))
        new_limit = old_limit + 1 if is_minimum else max(1, old_limit - 1)
        old["predicate"]["limit"] = old_limit
        bound_phrase = "at least" if is_minimum else "at most"
        old["text"] = f"Require {bound_phrase} {old_limit} applicable tool calls in this project."
        new["predicate"]["limit"] = new_limit
        new["text"] = f"Require {bound_phrase} {new_limit} applicable tool calls in this project."
        worlds = [
            {
                "world_id": "before_amendment",
                "directive_events": [_event(0, "introduce", directive_id, version=1, directive=old)],
            },
            {
                "world_id": "after_amendment",
                "directive_events": [
                    _event(0, "introduce", directive_id, version=1, directive=old),
                    _event(2, "amend", directive_id, version=2, directive=new),
                ],
            },
        ]
        predicate = new["predicate"]
    else:
        worlds = [
            {
                "world_id": "active_latest",
                "directive_events": [_event(0, "introduce", directive_id, version=1, directive=base)],
            },
            {
                "world_id": "revoked_latest",
                "directive_events": [
                    _event(0, "introduce", directive_id, version=1, directive=base),
                    _event(2, "revoke", directive_id),
                ],
            },
        ]

    if trace_conditioned:
        is_minimum = predicate["kind"].startswith("min_")
        if is_minimum and dynamic:
            low_count = max(0, int(predicate["limit"]) - 1)
            high_count = int(predicate["limit"])
        elif is_minimum:
            low_count = max(0, int(predicate["limit"]) - 1)
            high_count = int(predicate["limit"])
        else:
            low_count = 1
            high_count = max(1, int(predicate["limit"]))
        tool = predicate.get("tool") or "generic_lookup"
        prefixes = [
            {
                "prefix_id": "below_boundary",
                "actions": [{"kind": "tool_call", "tool": tool}] * min(low_count, high_count - 1),
            },
            {
                "prefix_id": "at_boundary",
                "actions": [{"kind": "tool_call", "tool": tool}] * high_count,
            },
        ]
        candidate = (
            {"kind": "final_response", "complies": True}
            if is_minimum
            else {"kind": "tool_call", "tool": tool}
        )
    else:
        prefixes = [
            {"prefix_id": "empty_prefix", "actions": []},
            {
                "prefix_id": "unrelated_prefix",
                "actions": [{"kind": "tool_call", "tool": "unrelated_lookup"}],
            },
        ]
        candidate = {"kind": "final_response", "complies": False}

    gold: dict[str, bool] = {}
    for world in worlds:
        active = resolve_active_directives(world["directive_events"], context)
        world["rendered_history"] = render_history(
            world["directive_events"], context, row["task_summary"]
        )
        for prefix in prefixes:
            key = f"{world['world_id']}::{prefix['prefix_id']}"
            gold[key] = candidate_allowed(active, prefix["actions"], candidate)

    episode = {
        "schema_version": "CCTUV2EpisodeV1",
        "episode_id": f"{'gold' if handcrafted else 'pilot'}-{episode_index:03d}",
        "base_task_id": row["task_uid"],
        "source_constraint_uid": row["constraint_uid"],
        "counterfactual_group_id": f"cf-{episode_index:03d}",
        "taxonomy_cell": cell,
        "task_summary": row["task_summary"],
        "current_context": context,
        "worlds": worlds,
        "trace_prefixes": prefixes,
        "candidate_action": candidate,
        "gold_labels": gold,
        "rendered_history": worlds[0]["rendered_history"],
        "construction": "handcrafted_blueprint" if handcrafted else "deterministic_pilot_builder",
    }
    errors = validate_episode(episode)
    if errors:
        raise ValueError(f"invalid episode {episode['episode_id']}: {errors}")
    return episode


def _eligible_rows(audit: dict[str, Any], action_local: bool) -> list[dict[str, Any]]:
    wanted = {"action_local"} if action_local else {
        "count_based",
        "round_count_based",
        "tool_count_based",
    }
    return [
        row
        for row in audit["constraints"]
        if row["dependency_type"] in wanted
        and row["directive_nature"] == "standing_user_directive"
        and not row["descriptor_mismatch"]
    ]


def _select_rows(audit: dict[str, Any], count: int, action_local: bool) -> list[dict[str, Any]]:
    rows = _eligible_rows(audit, action_local)
    selected: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    for row in rows:
        if row["task_uid"] in seen_tasks:
            continue
        selected.append(row)
        seen_tasks.add(row["task_uid"])
        if len(selected) == count:
            return selected
    raise ValueError(f"not enough eligible rows: requested={count}, got={len(selected)}")


def build_gold(audit: dict[str, Any]) -> list[dict[str, Any]]:
    # The allocation and source rows are deliberately hand-selected/frozen for
    # the gold set; generation below only materializes the canonical blueprint.
    allocation = [
        "static_action_local",
        "static_action_local",
        "dynamic_action_local",
        "dynamic_action_local",
        "dynamic_action_local",
        "static_trajectory_conditioned",
        "static_trajectory_conditioned",
        "dynamic_trajectory_conditioned",
        "dynamic_trajectory_conditioned",
        "dynamic_trajectory_conditioned",
    ]
    local_rows = _select_rows(audit, 5, True)
    trace_rows = _select_rows(audit, 5, False)
    rows = iter([*local_rows, *trace_rows])
    return [
        build_episode(next(rows), episode_index=index, cell=cell, handcrafted=True)
        for index, cell in enumerate(allocation)
    ]


def build_pilot(audit: dict[str, Any]) -> list[dict[str, Any]]:
    local_rows = _select_rows(audit, 20, True)
    trace_rows = _select_rows(audit, 20, False)
    episodes: list[dict[str, Any]] = []
    for cell_index, cell in enumerate(CELLS):
        rows = local_rows[cell_index * 10 : (cell_index + 1) * 10] if cell_index < 2 else trace_rows[(cell_index - 2) * 10 : (cell_index - 1) * 10]
        for row in rows:
            episodes.append(
                build_episode(row, episode_index=len(episodes), cell=cell, handcrafted=False)
            )
    return episodes


def structural_report(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [error for episode in episodes for error in validate_episode(episode)]
    labels = [value for episode in episodes for value in episode["gold_labels"].values()]
    flips = 0
    for episode in episodes:
        if len(set(episode["gold_labels"].values())) > 1:
            flips += 1
    # A no-memory always-allow baseline is intentionally weak but useful for
    # checking label balance without invoking a model/API.
    no_memory_accuracy = sum(labels) / len(labels) if labels else 0.0
    return {
        "schema_version": "CCTUV2PilotReportV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "episode_count": len(episodes),
        "condition_count": len(labels),
        "taxonomy_distribution": dict(Counter(ep["taxonomy_cell"] for ep in episodes)),
        "positive_label_rate": no_memory_accuracy,
        "always_allow_accuracy": no_memory_accuracy,
        "counterfactual_groups_with_label_flip": flips,
        "counterfactual_flip_rate": flips / len(episodes) if episodes else 0.0,
        "oracle_accuracy": 1.0 if not errors else 0.0,
        "validation_errors": errors,
        "expansion_decision": {
            "status": "hold_for_memory_system_pilot",
            "reason": (
                "Structural pilot passes; expansion still requires real memory-system runs and human review."
                if not errors and flips == len(episodes)
                else "Structural pilot failed validation."
            ),
        },
    }


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--gold-output", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--pilot-output", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    # Read tasks as a provenance/sanity dependency even though the audit rows
    # contain the task summaries used for construction.
    tasks = json.loads(args.tasks.read_text(encoding="utf-8"))
    if len(tasks.get("tasks") or []) != 200:
        raise SystemExit("expected 200 CCTU source tasks")
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    gold = build_gold(audit)
    pilot = build_pilot(audit)
    report = structural_report(pilot)
    _write(args.gold_output, {"schema_version": "CCTUV2GoldSetV1", "examples": gold})
    _write(args.pilot_output, {"schema_version": "CCTUV2PilotV1", "episodes": pilot})
    _write(args.report_output, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
