#!/usr/bin/env python3
"""Grade MAC-CCTU noisy evaluator specs against a memory-eval run output."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.agent.trajectory import build_raw_history  # noqa: E402
from bench.MAC.cctu.bridge import MAC_CCTU_DATA_DIR, cctu_samples_by_id, load_cctu_eval_tasks  # noqa: E402
from bench.MAC.cctu.grade_answer import grade_one  # noqa: E402
from bench.MAC.construct.sop.noise_eval import (  # noqa: E402
    contract_metrics,
    follow_outcome,
    follow_taxonomy_metrics,
)
from bench.MAC.grading.score_format import (  # noqa: E402
    build_grade_document,
    format_cctu_legacy_scores,
    format_main_scores,
)
from bench.MAC.scripts.run_paths import bench_grade_path, make_run_unique_index  # noqa: E402

DEFAULT_MANIFEST = Path("bench/MAC/cctu/data/mac-cctu-noise_eval_specs.json")
DEFAULT_OUTPUT = Path("bench/MAC/cctu/results/noise_eval_grade.json")
DEFAULT_TASKS = Path("bench/MAC/cctu/data/mac-cctu-tasks.json")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answers_file", type=Path, help="JSON output from bench/MAC/scripts/run_memory_eval.py")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--bench", choices=["cctu"], default="cctu")
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard", "all"])
    parser.add_argument("--memory-system")
    parser.add_argument("--run-id")
    parser.add_argument("--detail", action="store_true")
    return parser.parse_args()


def infer_memory_system(args: argparse.Namespace, header: dict[str, Any]) -> str:
    return str(args.memory_system or header.get("memory_system") or "unknown")


def output_path(
    args: argparse.Namespace,
    *,
    header: dict[str, Any],
    memory_system: str,
) -> Path:
    if args.output:
        return args.output
    run_id = args.run_id or header.get("run_id") or make_run_unique_index()
    if args.output_dir:
        return args.output_dir / f"{memory_system}_{args.bench}_{run_id}.json"
    return bench_grade_path(memory_system, args.bench, str(run_id))


def read_memory_output(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    header = payload.get("header")
    records = payload.get("records")
    if isinstance(header, dict) and isinstance(records, list):
        return header, [row for row in records if isinstance(row, dict)]
    raise ValueError(f"{path} is not a MACMemoryOutputV1 file")


def load_artifact(path: str) -> dict[str, Any]:
    payload = load_json(Path(path))
    if not isinstance(payload, dict):
        raise ValueError(f"evaluator artifact must be a JSON object: {path}")
    return payload


def flatten_tool_calls(raw_history: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for step in raw_history.get("trajectory") or []:
        if not isinstance(step, dict):
            continue
        iteration = step.get("iteration")
        for call in step.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            calls.append(
                {
                    "index": len(calls),
                    "iteration": iteration,
                    "name": call.get("name"),
                    "arguments": call.get("arguments") if isinstance(call.get("arguments"), dict) else {},
                    "result": call.get("result"),
                }
            )
    return calls


def trace_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = build_raw_history(row)
    return {
        "final_response": raw.get("final_response", ""),
        "trajectory": raw.get("trajectory", []),
        "tool_calls": flatten_tool_calls(raw),
    }


def verdict(observed: bool | None, confidence: str, reason: str, evidence_refs: list[Any] | None = None) -> dict[str, Any]:
    return {
        "observed_followed": observed,
        "confidence": confidence,
        "reason": reason,
        "evidence_refs": evidence_refs or [],
    }


def task_responded(row: dict[str, Any]) -> bool:
    for event in row.get("events") or []:
        if not isinstance(event, dict):
            continue
        if event.get("event") != "tool_result" or event.get("name") != "send_message":
            continue
        result = event.get("result")
        terminal = event.get("terminal") is True
        if isinstance(result, dict):
            terminal = terminal or result.get("terminal") is True or result.get("ok") is True
        if terminal:
            return True
    return row.get("stop_reason") == "send_message" and bool(str(row.get("final_answer") or "").strip())


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def has_markdown(text: str) -> bool:
    return bool(re.search(r"(^|\n)#{1,6}\s+|\*\*[^*]+\*\*|`[^`]+`|(^|\n)\s*[-*]\s+", text))


def contains_json_object(text: str, *, whole_response: bool) -> bool:
    candidates = [text.strip()] if whole_response else re.findall(r"\{.*?\}", text, flags=re.DOTALL)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:  # noqa: BLE001 - candidate extraction is best-effort.
            continue
        if isinstance(parsed, dict):
            return True
    return False


def date_pattern(fmt: str) -> str:
    if fmt == "iso":
        return r"\b\d{4}-\d{2}-\d{2}\b"
    if fmt == "slash":
        return r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    if fmt == "month_year":
        return r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{4}\b|\b\d{4}-\d{2}\b"
    return r"\b\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b"


def eval_response_format(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    response = str(trace.get("final_response") or "")
    if not response:
        return verdict(None, "unknown", "missing final response")
    failed: list[str] = []
    evidence: list[dict[str, Any]] = [{"field": "final_response"}]
    for check in spec.get("checks") or []:
        if not isinstance(check, dict):
            failed.append("invalid check object")
            continue
        name = str(check.get("name") or "")
        if name == "markdown_any" and not has_markdown(response):
            failed.append("expected Markdown formatting")
        elif name == "bold_any" and not re.search(r"\*\*[^*]+\*\*", response):
            failed.append("expected bold Markdown text")
        elif name == "no_markdown" and has_markdown(response):
            failed.append("expected no Markdown formatting")
        elif name == "plain_text" and (has_markdown(response) or contains_json_object(response, whole_response=True)):
            failed.append("expected plain text response")
        elif name == "json_object" and not contains_json_object(response, whole_response=True):
            failed.append("expected whole response to be a JSON object")
        elif name == "json_contains_object" and not contains_json_object(response, whole_response=False):
            failed.append("expected response to contain a JSON object")
        elif name == "contains_terms":
            terms = [str(term).lower() for term in check.get("terms") or []]
            missing = [term for term in terms if term and term not in response.lower()]
            if missing:
                failed.append(f"missing terms: {missing[:5]}")
        elif name == "excludes_terms":
            terms = [str(term).lower() for term in check.get("terms") or []]
            present = [term for term in terms if term and term in response.lower()]
            if present:
                failed.append(f"forbidden terms present: {present[:5]}")
        elif name == "starts_with":
            value = str(check.get("value") or "")
            if value and not response.startswith(value):
                failed.append(f"response does not start with {value!r}")
        elif name == "ends_with":
            value = str(check.get("value") or "")
            if value and not response.rstrip().endswith(value):
                failed.append(f"response does not end with {value!r}")
        elif name == "date_format":
            if not re.search(date_pattern(str(check.get("format") or "any")), response, flags=re.IGNORECASE):
                failed.append("expected date in requested format")
        else:
            failed.append(f"unsupported response_format check: {name}")
    if failed:
        return verdict(False, "medium", "; ".join(failed), evidence)
    return verdict(True, "medium", "all response format checks passed", evidence)


def eval_response_length(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    response = str(trace.get("final_response") or "")
    if not response:
        return verdict(None, "unknown", "missing final response")
    unit = spec.get("unit")
    count = word_count(response) if unit == "words" else len(response)
    min_value = spec.get("min")
    max_value = spec.get("max")
    if isinstance(min_value, int) and count < min_value:
        return verdict(False, "high", f"{unit} count {count} below minimum {min_value}")
    if isinstance(max_value, int) and count > max_value:
        return verdict(False, "high", f"{unit} count {count} above maximum {max_value}")
    return verdict(True, "high", f"{unit} count {count} within bounds")


def eval_tool_call_count(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    count = len(trace.get("tool_calls") or [])
    min_value = spec.get("min")
    max_value = spec.get("max")
    if isinstance(min_value, int) and count < min_value:
        return verdict(False, "high", f"tool call count {count} below minimum {min_value}")
    if isinstance(max_value, int) and count > max_value:
        return verdict(False, "high", f"tool call count {count} above maximum {max_value}")
    return verdict(True, "high", f"tool call count {count} within bounds")


def eval_interaction_rounds(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    count = len(trace.get("trajectory") or [])
    min_value = spec.get("min")
    max_value = spec.get("max")
    if isinstance(min_value, int) and count < min_value:
        return verdict(False, "high", f"assistant round count {count} below minimum {min_value}")
    if isinstance(max_value, int) and count > max_value:
        return verdict(False, "high", f"assistant round count {count} above maximum {max_value}")
    return verdict(True, "high", f"assistant round count {count} within bounds")


def eval_specific_tool_call_count(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(str(call.get("name") or "") for call in trace.get("tool_calls") or [])
    failures: list[str] = []
    for tool, bounds in (spec.get("per_tool") or {}).items():
        if not isinstance(bounds, dict):
            continue
        count = counts.get(str(tool), 0)
        min_value = bounds.get("min")
        max_value = bounds.get("max")
        if isinstance(min_value, int) and count < min_value:
            failures.append(f"{tool}: {count} below {min_value}")
        if isinstance(max_value, int) and count > max_value:
            failures.append(f"{tool}: {count} above {max_value}")
    if failures:
        return verdict(False, "high", "; ".join(failures))
    return verdict(True, "high", "per-tool call counts within bounds")


def eval_tool_sequence(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    calls = trace.get("tool_calls") or []
    earliest: dict[str, int] = {}
    for index, call in enumerate(calls):
        name = str(call.get("name") or "")
        earliest.setdefault(name, index)
    failures: list[str] = []
    for order in spec.get("orders") or []:
        if not isinstance(order, list):
            continue
        previous = -1
        for tool in [str(item) for item in order]:
            index = earliest.get(tool)
            if index is None:
                failures.append(f"{tool} was not called")
                break
            if index <= previous:
                failures.append(f"order not satisfied: {order}")
                break
            previous = index
    if failures:
        return verdict(False, "high", "; ".join(failures))
    return verdict(True, "high", "tool order constraints satisfied")


def eval_tool_parallel(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    steps = trace.get("trajectory") or []
    step_sets = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_sets.append({str(call.get("name") or "") for call in step.get("tool_calls") or [] if isinstance(call, dict)})
    failures: list[str] = []
    for group in spec.get("groups") or []:
        expected = {str(item) for item in group if item}
        if expected and not any(expected <= names for names in step_sets):
            failures.append(f"group not called in same step: {sorted(expected)}")
    if failures:
        return verdict(False, "high", "; ".join(failures))
    return verdict(True, "high", "parallel tool groups satisfied")


def eval_parallel_call_count(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    unit = str(spec.get("unit") or "type")
    max_seen = 0
    failures: list[str] = []
    for step in trace.get("trajectory") or []:
        if not isinstance(step, dict):
            continue
        calls = [call for call in step.get("tool_calls") or [] if isinstance(call, dict)]
        current = len({str(call.get("name") or "") for call in calls}) if unit == "type" else len(calls)
        max_seen = max(max_seen, current)
        max_value = spec.get("max")
        if isinstance(max_value, int) and current > max_value:
            failures.append(f"parallel call count {current} above maximum {max_value}")
    min_value = spec.get("min")
    if isinstance(min_value, int) and max_seen < min_value:
        failures.append(f"maximum observed parallel call count {max_seen} below minimum {min_value}")
    if failures:
        return verdict(False, "high", "; ".join(failures))
    return verdict(True, "high", f"parallel call count within bounds; max_seen={max_seen}")


def eval_tool_usage(spec: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    called = {str(call.get("name") or "") for call in trace.get("tool_calls") or []}
    required = {str(item) for item in spec.get("required_tools") or []}
    forbidden = {str(item) for item in spec.get("forbidden_tools") or []}
    missing = sorted(required - called)
    present_forbidden = sorted(forbidden & called)
    failures = []
    if missing:
        failures.append(f"required tools not called: {missing}")
    if present_forbidden:
        failures.append(f"forbidden tools called: {present_forbidden}")
    if failures:
        return verdict(False, "high", "; ".join(failures))
    return verdict(True, "high", "tool usage constraints satisfied")


STRUCTURED_EVALUATORS = {
    "interaction_rounds": eval_interaction_rounds,
    "parallel_call_count": eval_parallel_call_count,
    "response_format": eval_response_format,
    "response_length": eval_response_length,
    "tool_call_count": eval_tool_call_count,
    "specific_tool_call_count": eval_specific_tool_call_count,
    "tool_sequence": eval_tool_sequence,
    "tool_parallel": eval_tool_parallel,
    "tool_usage": eval_tool_usage,
}


BLOCKED_CALLS = {"open", "eval", "exec", "compile", "__import__", "input", "globals", "locals", "vars"}
ALLOWED_IMPORTS = {
    "collections",
    "csv",
    "datetime",
    "decimal",
    "io",
    "json",
    "math",
    "re",
    "string",
    "typing",
    "unicodedata",
}


def verify_python_code(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    errors: list[str] = []
    evaluate = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "evaluate"), None)
    if evaluate is None:
        errors.append("missing evaluate(trace)")
    elif [arg.arg for arg in evaluate.args.args] != ["trace"]:
        errors.append("evaluate signature must be evaluate(trace)")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", 1)[0] not in ALLOWED_IMPORTS:
                    errors.append(f"disallowed import: {alias.name}")
        if isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".", 1)[0]
            if module not in ALLOWED_IMPORTS:
                errors.append(f"disallowed import: {node.module}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            errors.append(f"blocked call: {node.func.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            errors.append("dunder attribute access is not allowed")
    return sorted(set(errors))


def eval_python(code_path: str, trace: dict[str, Any]) -> dict[str, Any]:
    path = resolve_path(Path(code_path))
    code = path.read_text(encoding="utf-8")
    errors = verify_python_code(code)
    if errors:
        return verdict(None, "unknown", "python evaluator rejected: " + "; ".join(errors))
    module_name = "noise_eval_" + re.sub(r"[^A-Za-z0-9_]", "_", str(path.relative_to(REPO_ROOT)))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return verdict(None, "unknown", f"could not load evaluator: {code_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        result = module.evaluate(trace)
    except Exception as exc:  # noqa: BLE001 - one bad evaluator should not abort the grade.
        return verdict(None, "unknown", f"python evaluator failed: {type(exc).__name__}: {exc}")
    if not isinstance(result, dict):
        return verdict(None, "unknown", "python evaluator returned non-dict")
    observed = result.get("observed_followed")
    if observed not in {True, False, None}:
        observed = None
    return {
        "observed_followed": observed,
        "confidence": str(result.get("confidence") or ("unknown" if observed is None else "low")),
        "reason": str(result.get("reason") or ""),
        "evidence_refs": result.get("evidence_refs") if isinstance(result.get("evidence_refs"), list) else [],
    }


def evaluate_artifact(artifact: dict[str, Any], unit: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    evaluator = artifact.get("evaluator") if isinstance(artifact.get("evaluator"), dict) else {}
    if evaluator.get("status") != "success":
        return verdict(None, "unknown", "; ".join(str(item) for item in evaluator.get("notes") or ["unsupported evaluator"]))
    evaluator_type = evaluator.get("evaluator_type")
    if evaluator_type == "structured":
        family = evaluator.get("family")
        spec = evaluator.get("spec")
        if not isinstance(family, str) or not isinstance(spec, dict):
            return verdict(None, "unknown", "structured evaluator missing family/spec")
        fn = STRUCTURED_EVALUATORS.get(family)
        if fn is None:
            return verdict(None, "unknown", f"unsupported structured family: {family}")
        return fn(spec, trace)
    if evaluator_type == "python":
        code_path = unit.get("code_path")
        if not isinstance(code_path, str) or not code_path:
            return verdict(None, "unknown", "python evaluator missing code_path")
        return eval_python(code_path, trace)
    return verdict(None, "unknown", f"unsupported evaluator_type: {evaluator_type}")


def outcome_bucket(expected: bool, observed: bool | None) -> str:
    if observed is None:
        return "anchor_missed" if expected else "noise_ignored"
    if expected and observed:
        return "anchor_followed"
    if expected and not observed:
        return "anchor_missed"
    if not expected and observed:
        return "noise_followed"
    return "noise_ignored"


def cctu_task_metrics(task_grades: dict[str, dict[str, Any]]) -> dict[str, float | None]:
    """Aggregate CCTU task and process-constraint metrics."""
    graded = [grade for grade in task_grades.values() if not grade.get("error")]
    if not graded:
        return {
            "joint pass": None,
            "answer pass": None,
            "constraint pass": None,
            "constraint violation rate": None,
            "step pass rate": None,
            "ACC": None,
            "SR": None,
            "PSR": None,
            "SSR": None,
        }
    constraint_total = sum(int(grade.get("constraint_total") or 0) for grade in graded)
    constraint_satisfied = sum(int(grade.get("constraint_satisfied") or 0) for grade in graded)
    unsolved_slot_total = sum(int(grade.get("unsolved_slot_total") or 0) for grade in graded)
    unsolved_slot_satisfied = sum(int(grade.get("unsolved_slot_satisfied") or 0) for grade in graded)
    constraint_violated = max(0, constraint_total - constraint_satisfied)
    return {
        "joint pass": sum(1 for grade in graded if grade.get("joint_pass")) / len(graded),
        "answer pass": sum(1 for grade in graded if grade.get("answer_pass")) / len(graded),
        "constraint pass": sum(1 for grade in graded if grade.get("constraint_pass")) / len(graded),
        "constraint violation rate": (
            constraint_violated / constraint_total if constraint_total else 0.0
        ),
        "step pass rate": (
            unsolved_slot_satisfied / unsolved_slot_total if unsolved_slot_total else 1.0
        ),
        "ACC": sum(1 for grade in graded if grade.get("acc")) / len(graded),
        "SR": sum(1 for grade in graded if grade.get("SR")) / len(graded),
        "PSR": sum(1 for grade in graded if grade.get("PSR")) / len(graded),
        "SSR": sum(float(grade.get("SSR") or 0.0) for grade in graded) / len(graded),
    }


def build_main_score_values(
    details: list[dict[str, Any]],
    task_grades: dict[str, dict[str, Any]],
    task_rsp: dict[str, bool] | None = None,
) -> dict[str, float | None]:
    cctu_scores = cctu_task_metrics(task_grades)
    return {
        "joint pass": cctu_scores["joint pass"],
        "answer pass": cctu_scores["answer pass"],
        "constraint pass": cctu_scores["constraint pass"],
        "constraint violation rate": cctu_scores["constraint violation rate"],
    }


def build_contract_diagnostics(details: list[dict[str, Any]]) -> dict[str, Any]:
    contract = follow_taxonomy_metrics(details)
    return {
        "constraint_follow_scores": {
            "correct_follow_rate": contract["correct_follow_rate"],
            "wrong_follow_rate": contract["wrong_follow_rate"],
            "neither_follow_rate": contract["neither_follow_rate"],
        },
        "support": {
            "comparison_count": contract["comparison_count"],
            "constraint_count": contract["constraint_count"],
            "active_constraint_count": contract["active_constraint_count"],
            "history_constraint_count": contract["history_constraint_count"],
            "correctly_followed": contract["correctly_followed"],
            "wrongly_followed": contract["wrongly_followed"],
            "neither_followed": contract["neither_followed"],
        },
    }


def build_scope_follow_details(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in details:
        task_uid = str(row.get("task_uid") or "")
        source_uid = str(row.get("source_constraint_uid") or row.get("node_id") or "")
        if not task_uid or not source_uid:
            continue
        grouped[(task_uid, source_uid)].append(row)

    follow_details: list[dict[str, Any]] = []
    for (task_uid, source_uid), rows in sorted(grouped.items()):
        active_rows = [row for row in rows if row.get("expected_should_apply")]
        history_rows = [row for row in rows if not row.get("expected_should_apply")]
        anchor_matched = any(row.get("observed_followed") is True for row in active_rows)
        history_matched = any(row.get("observed_followed") is True for row in history_rows)
        first = rows[0]
        follow_details.append(
            {
                "task_uid": task_uid,
                "source_constraint_uid": source_uid,
                "source_anchor_role": first.get("source_anchor_role"),
                "family": first.get("family"),
                "follow_outcome": follow_outcome(anchor_matched, history_matched),
                "anchor_matched": anchor_matched,
                "history_matched": history_matched,
                "active_constraint_count": len(active_rows),
                "history_constraint_count": len(history_rows),
                "history_hit_count": sum(1 for row in history_rows if row.get("observed_followed") is True),
            }
        )
    return follow_details


def score_rows(
    details: list[dict[str, Any]],
    task_grades: dict[str, dict[str, Any]],
    task_rsp: dict[str, bool] | None = None,
) -> dict[str, Any]:
    contract = contract_metrics(details)
    cctu_scores = cctu_task_metrics(task_grades)
    task_rsp = task_rsp or {}
    graded_tasks = [grade for grade in task_grades.values() if not grade.get("error")]
    return {
        **build_main_score_values(details, task_grades, task_rsp),
        **cctu_scores,
        "constraint_follow_support": {
            "constraint_count": contract["constraint_count"],
            "active_constraint_count": contract["active_constraint_count"],
            "history_constraint_count": contract["history_constraint_count"],
            "correctly_followed": contract["correctly_followed"],
            "wrongly_followed": contract["wrongly_followed"],
        },
        "support": {
            "task_count": len(task_grades),
            "cctu_graded_task_count": len(graded_tasks),
            "rsp_task_count": len(task_rsp),
        },
    }


def grouped_main_scores(
    details: list[dict[str, Any]],
    key: str,
    task_grades: dict[str, dict[str, Any]],
    task_rsp: dict[str, bool],
) -> dict[str, list[dict[str, Any]]]:
    grouped_details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in details:
        grouped_details[str(row.get(key) or "unknown")].append(row)
    score_groups: dict[str, list[dict[str, Any]]] = {}
    for name, rows in sorted(grouped_details.items()):
        task_uids = {str(row.get("task_uid") or "") for row in rows}
        group_grades = {task_uid: task_grades[task_uid] for task_uid in task_uids if task_uid in task_grades}
        group_rsp = {task_uid: task_rsp[task_uid] for task_uid in task_uids if task_uid in task_rsp}
        score_groups[name] = format_main_scores(build_main_score_values(rows, group_grades, group_rsp))
    return score_groups


def grouped_by_data_source(
    details: list[dict[str, Any]],
    task_grades: dict[str, dict[str, Any]],
    task_rsp: dict[str, bool],
    tasks_by_uid: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped_details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in details:
        task_uid = str(row.get("task_uid") or "")
        task = tasks_by_uid.get(task_uid) or {}
        source = str(task.get("data_source") or task.get("cctu_data_source") or "Unknown")
        grouped_details[source].append(row)

    score_groups: dict[str, list[dict[str, Any]]] = {}
    all_task_uids = set(task_grades)
    overall_rows = [row for row in details if str(row.get("task_uid") or "") in all_task_uids]
    score_groups["Overall"] = format_main_scores(
        build_main_score_values(overall_rows, task_grades, task_rsp)
    )
    for name, rows in sorted(grouped_details.items()):
        task_uids = {str(row.get("task_uid") or "") for row in rows}
        group_grades = {task_uid: task_grades[task_uid] for task_uid in task_uids if task_uid in task_grades}
        group_rsp = {task_uid: task_rsp[task_uid] for task_uid in task_uids if task_uid in task_rsp}
        score_groups[name] = format_main_scores(build_main_score_values(rows, group_grades, group_rsp))
    return score_groups


def main() -> int:
    args = parse_args()
    header, records = read_memory_output(args.answers_file)
    manifest = load_json(args.manifest)
    units = manifest.get("units") if isinstance(manifest, dict) else None
    if not isinstance(units, list):
        raise ValueError("manifest must contain units list")
    rows_by_task = {
        str(row.get("task_uid")): row
        for row in records
        if row.get("record_type") == "task_result" and row.get("task_uid")
    }
    tasks, _summary = load_cctu_eval_tasks(data_dir=MAC_CCTU_DATA_DIR)
    tasks_by_uid = {str(task.get("task_uid")): task for task in tasks if isinstance(task, dict)}
    samples = cctu_samples_by_id()
    task_grades = {
        task_uid: grade_one(row, tasks_by_uid.get(task_uid), samples)
        for task_uid, row in rows_by_task.items()
    }
    task_rsp = {task_uid: task_responded(row) for task_uid, row in rows_by_task.items()}
    traces = {task_uid: trace_from_row(row) for task_uid, row in rows_by_task.items()}
    details: list[dict[str, Any]] = []
    missing_tasks = 0
    for unit in units:
        if not isinstance(unit, dict):
            continue
        task_uid = str(unit.get("task_uid") or "")
        trace = traces.get(task_uid)
        if trace is None:
            missing_tasks += 1
            continue
        artifact_path = unit.get("artifact_path")
        if not isinstance(artifact_path, str):
            continue
        artifact = load_artifact(artifact_path)
        result = evaluate_artifact(artifact, unit, trace)
        expected = bool(unit.get("expected_should_apply"))
        observed = result.get("observed_followed")
        outcome = outcome_bucket(expected, observed if observed in {True, False, None} else None)
        details.append(
            {
                "task_uid": task_uid,
                "node_id": unit.get("node_id"),
                "source_constraint_uid": unit.get("source_constraint_uid"),
                "source_anchor_role": unit.get("source_anchor_role"),
                "is_anchor": unit.get("is_anchor"),
                "family": unit.get("family"),
                "evaluator_type": unit.get("evaluator_type"),
                "expected_should_apply": expected,
                "observed_followed": observed,
                "observed_followed_raw": observed,
                "confidence": result.get("confidence"),
                "reason": result.get("reason"),
                "outcome": outcome,
                "evidence_refs": result.get("evidence_refs", []),
            }
        )

    scope_follow_details = build_scope_follow_details(details)
    payload = build_grade_document(
        scores=format_main_scores(build_main_score_values(details, task_grades, task_rsp)),
        schema_version="MACCCTUGradeV2",
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_answers=str(args.answers_file),
        source_manifest=str(args.manifest),
        bench=args.bench,
        difficulty=args.difficulty,
        memory_system=infer_memory_system(args, header),
        run_header={
            "run_id": header.get("run_id"),
            "bench": header.get("bench"),
            "memory_system": header.get("memory_system"),
        },
        graded_unit_count=len(details),
        missing_task_unit_count=missing_tasks,
        task_error_count=sum(1 for row in records if row.get("record_type") == "task_error"),
        graded_task_count=len(task_grades),
        appendix_scores={
            "legacy_cctu_task_metrics": format_cctu_legacy_scores(cctu_task_metrics(task_grades)),
        },
        score_groups=grouped_by_data_source(details, task_grades, task_rsp, tasks_by_uid),
        constraint_follow_analysis=build_contract_diagnostics(scope_follow_details),
        contract_diagnostics=build_contract_diagnostics(scope_follow_details),
        task_scores={
            task_uid: {
                "joint pass": grade.get("joint_pass"),
                "answer pass": grade.get("answer_pass"),
                "constraint pass": grade.get("constraint_pass"),
                "constraint violation rate": grade.get("constraint_violation_rate"),
                "step pass rate": grade.get("step_pass_rate"),
                "RSP": task_rsp.get(task_uid),
                "legacy_ACC": grade.get("acc"),
                "SR": grade.get("SR"),
                "PSR": grade.get("PSR"),
                "SSR": grade.get("SSR"),
                **({"error": grade["error"]} if grade.get("error") else {}),
            }
            for task_uid, grade in sorted(task_grades.items())
        },
        scores_by_family=grouped_main_scores(details, "family", task_grades, task_rsp),
        scores_by_source_anchor_role=grouped_main_scores(
            details, "source_anchor_role", task_grades, task_rsp
        ),
        details=details if args.detail else [],
        contract_follow_details=scope_follow_details if args.detail else [],
    )
    target = output_path(args, header=header, memory_system=infer_memory_system(args, header))
    write_json(target, payload)
    print(json.dumps(payload["scores"], indent=2, ensure_ascii=False))
    print(f"Wrote {resolve_path(target)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
