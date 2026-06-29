#!/usr/bin/env python3
"""Audit MAC-CCTU noise evaluator artifacts before benchmark grading.

This is a lightweight agent-verification scaffold for the generated
``noise_check_code`` artifacts.  It does not replace human annotation, but it
does separate obviously healthy evaluators from ones worth reviewing by hand.
"""

from __future__ import annotations

import argparse
import ast
import json
import random
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.construct.cctu.noise_eval_generation import verify_package  # noqa: E402
from bench.construct.cctu.noise_eval_grade import evaluate_artifact  # noqa: E402

DEFAULT_ARTIFACT_DIR = Path("bench/MAC/cctu/data/noise_check_code")
DEFAULT_OUTPUT = Path("bench/cctu/mid_data/eval_step5_5_noise_eval_verify.json")


@dataclass(frozen=True)
class VerifyJob:
    ordinal: int
    artifact_path: Path


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def repo_relative(path: Path) -> str:
    try:
        return str(resolve_path(path).relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def iter_artifact_paths(artifact_dir: Path) -> list[Path]:
    root = resolve_path(artifact_dir)
    if not root.exists():
        raise FileNotFoundError(f"artifact dir does not exist: {root}")
    paths = [
        path
        for path in root.rglob("*.json")
        if path.is_file() and path.name != ".DS_Store"
    ]
    return sorted(paths)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, help="Audit only N artifacts after sampling.")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--include-passing", action="store_true", help="Include all passing item details.")
    parser.add_argument("--max-details", type=int, default=500, help="Maximum item details in report unless --include-passing.")
    parser.add_argument("--print-examples", type=int, default=10, help="Print up to N flagged examples.")
    return parser.parse_args()


def code_path_for_artifact(path: Path) -> Path:
    return path.with_suffix(".py")


def artifact_package(artifact: dict[str, Any], code_path: Path | None) -> dict[str, Any]:
    evaluator = artifact.get("evaluator") if isinstance(artifact.get("evaluator"), dict) else {}
    package = dict(evaluator)
    if package.get("evaluator_type") == "python" and code_path is not None and code_path.exists():
        package["check_code"] = code_path.read_text(encoding="utf-8")
    return package


def text_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower()))


FEATURE_TERMS: dict[str, tuple[str, ...]] = {
    "json": ("json",),
    "markdown": ("markdown", "bold", "heading", "bullet", "list", "emphasis", "format"),
    "length": ("word", "words", "character", "characters", "sentence", "sentences", "length"),
    "tool_count": ("tool", "tools", "call", "calls", "invoke", "invocation", "invocations", "round", "interaction"),
    "tool_usage": ("tool", "tools", "call", "calls", "invoke", "use", "retriever", "analyzer", "finder", "tracker"),
    "date": ("date", "year", "month", "day", "timestamp"),
}

FAMILY_FEATURES: dict[str, tuple[str, ...]] = {
    "interaction_rounds": ("tool_count",),
    "parallel_call_count": ("tool_count",),
    "response_format": ("markdown", "json", "date"),
    "response_length": ("length",),
    "tool_call_count": ("tool_count",),
    "specific_tool_call_count": ("tool_count", "tool_usage"),
    "tool_sequence": ("tool_count", "tool_usage"),
    "tool_parallel": ("tool_count", "tool_usage"),
    "tool_usage": ("tool_usage",),
}


def feature_mentions_constraint(feature: str, constraint: str, type_hint: list[str]) -> bool:
    tokens = text_tokens(constraint + " " + " ".join(type_hint))
    return any(term in tokens for term in FEATURE_TERMS.get(feature, (feature,)))


def mentioned_features(constraint: str, type_hint: list[str]) -> set[str]:
    return {
        feature
        for feature in FEATURE_TERMS
        if feature_mentions_constraint(feature, constraint, type_hint)
    }


def detect_code_features(code: str) -> set[str]:
    lower = code.lower()
    features: set[str] = set()
    if "json" in lower or "loads(" in lower:
        features.add("json")
    if any(token in lower for token in ("markdown", "**", "__", "heading", "bullet", r"\*\*")):
        features.add("markdown")
    if any(token in lower for token in ("word_count", "split()", "len(text", "len(response", "characters", "words")):
        features.add("length")
    if "tool_calls" in lower and any(token in lower for token in ("len(", "count", "at least", "at most", "exactly")):
        features.add("tool_count")
    if "tool_calls" in lower or "used_tools" in lower:
        features.add("tool_usage")
    if any(token in lower for token in ("date", "yyyy", "month", r"\d{4}", "timestamp")):
        features.add("date")
    return features


def ast_complexity_flags(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    flags: list[str] = []
    function_defs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    if len(function_defs) > 2:
        flags.append("complex_python_multiple_functions")
    call_names: Counter[str] = Counter()
    bool_ops = 0
    comparisons = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp):
            bool_ops += 1
        elif isinstance(node, ast.Compare):
            comparisons += 1
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_names[node.func.id] += 1
            elif isinstance(node.func, ast.Attribute):
                call_names[node.func.attr] += 1
    if bool_ops >= 8 or comparisons >= 18:
        flags.append("complex_python_many_conditions")
    if call_names["findall"] + call_names["finditer"] + call_names["search"] + call_names["match"] >= 10:
        flags.append("complex_python_many_regexes")
    return flags


def static_flags(artifact: dict[str, Any], code: str | None) -> list[str]:
    evaluator = artifact.get("evaluator") if isinstance(artifact.get("evaluator"), dict) else {}
    constraint = str(artifact.get("constraint_text") or "")
    type_hint = [str(item) for item in artifact.get("type_hint") or []]
    flags: list[str] = []

    evaluator_type = str(evaluator.get("evaluator_type") or "")
    if evaluator_type == "structured":
        family = str(evaluator.get("family") or "")
        spec = evaluator.get("spec") if isinstance(evaluator.get("spec"), dict) else {}
        if family == "response_format" and len(spec.get("checks") or []) > 1:
            flags.append("possible_over_strict_response_format_conjunction")
        expected_features = FAMILY_FEATURES.get(family, (family,))
        if family and not any(feature_mentions_constraint(feature, constraint, type_hint) for feature in expected_features):
            flags.append(f"structured_family_weakly_mentioned:{family}")
        uncovered = mentioned_features(constraint, type_hint) - set(expected_features)
        if len(uncovered) >= 2:
            flags.append("possible_composite_constraint_partially_covered")
        return flags

    if evaluator_type != "python" or not code:
        return flags

    features = detect_code_features(code)
    for feature in sorted(features):
        if not feature_mentions_constraint(feature, constraint, type_hint):
            flags.append(f"possible_redundant_{feature}_logic")
    flags.extend(ast_complexity_flags(code))

    lower_constraint = constraint.lower()
    lower_code = code.lower()
    if "markdown" in lower_constraint and all(token in lower_code for token in ("heading", "list", "bold")):
        flags.append("possible_over_strict_markdown_all_elements")
    if "json" in lower_constraint and any(token in lower_code for token in ("word", "character", "split()")):
        flags.append("possible_json_checker_contains_length_logic")
    if "tool" not in lower_constraint and "tool_calls" in lower_code:
        flags.append("possible_tool_logic_without_tool_constraint")
    return sorted(set(flags))


def synthetic_traces() -> list[tuple[str, dict[str, Any]]]:
    tool_calls = [
        {"index": 0, "iteration": 1, "name": "example_retriever", "arguments": {"query": "alpha"}, "result": "alpha"},
        {"index": 1, "iteration": 1, "name": "example_analyzer", "arguments": {"id": "alpha"}, "result": "beta"},
    ]
    return [
        ("empty", {"final_response": "", "trajectory": [], "tool_calls": []}),
        ("plain", {"final_response": "The answer is Paris.", "trajectory": [], "tool_calls": []}),
        ("json_object", {"final_response": '{"answer": "Paris", "date": "2020-01-01"}', "trajectory": [], "tool_calls": []}),
        ("markdown", {"final_response": "## Result\n\n- The date is **2020-01-01**.", "trajectory": [], "tool_calls": []}),
        ("tool_trace", {"final_response": "The answer is 2020-01-01 (example_retriever).", "trajectory": [], "tool_calls": tool_calls}),
    ]


def run_synthetic_cases(
    artifact: dict[str, Any],
    code_path: Path | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    unit = {"code_path": repo_relative(code_path)} if code_path is not None else {}
    results: list[dict[str, Any]] = []
    flags: list[str] = []
    observed_values: list[bool | None] = []
    for name, trace in synthetic_traces():
        result = evaluate_artifact(artifact, unit, trace)
        observed = result.get("observed_followed")
        if observed not in {True, False, None}:
            flags.append(f"synthetic_{name}_invalid_observed")
            observed = None
        observed_values.append(observed)
        results.append(
            {
                "case": name,
                "observed_followed": observed,
                "confidence": result.get("confidence"),
                "reason": result.get("reason"),
            }
        )
        if name == "empty" and observed is True:
            flags.append("empty_trace_passed")

    non_empty = observed_values[1:]
    return results, sorted(set(flags))


def severity(flags: list[str], verify_errors: list[str]) -> str:
    if verify_errors:
        return "fail"
    hard_prefixes = ("synthetic_", "possible_json_checker_contains_length")
    if any(flag.startswith(hard_prefixes) for flag in flags):
        return "needs_human"
    if flags:
        return "review"
    return "pass"


def verify_one(job: VerifyJob) -> dict[str, Any]:
    artifact_path = resolve_path(job.artifact_path)
    artifact = load_json(artifact_path)
    if not isinstance(artifact, dict):
        return {
            "artifact_path": repo_relative(artifact_path),
            "severity": "fail",
            "verify_errors": ["artifact is not a JSON object"],
            "flags": [],
        }

    evaluator = artifact.get("evaluator") if isinstance(artifact.get("evaluator"), dict) else {}
    evaluator_type = str(evaluator.get("evaluator_type") or "unknown")
    code_path = code_path_for_artifact(artifact_path) if evaluator_type == "python" else None
    code = code_path.read_text(encoding="utf-8") if code_path is not None and code_path.exists() else None
    package = artifact_package(artifact, code_path)
    verify_errors = verify_package(package)
    if evaluator_type == "python" and code_path is not None and not code_path.exists():
        verify_errors.append("python code file is missing")

    flags = static_flags(artifact, code)
    synthetic_results: list[dict[str, Any]] = []
    if evaluator.get("status") == "success" and not verify_errors:
        synthetic_results, synthetic_flags = run_synthetic_cases(artifact, code_path)
        flags.extend(synthetic_flags)

    item_severity = severity(sorted(set(flags)), verify_errors)
    return {
        "ordinal": job.ordinal,
        "artifact_path": repo_relative(artifact_path),
        "code_path": repo_relative(code_path) if code_path is not None else None,
        "task_uid": artifact.get("task_uid"),
        "node_id": artifact.get("node_id"),
        "constraint_text": artifact.get("constraint_text"),
        "expected_should_apply": artifact.get("expected_should_apply"),
        "is_anchor": artifact.get("is_anchor"),
        "type_hint": artifact.get("type_hint"),
        "evaluator_type": evaluator_type,
        "generation_method": (evaluator.get("generation") or {}).get("method") if isinstance(evaluator.get("generation"), dict) else None,
        "severity": item_severity,
        "verify_errors": sorted(set(verify_errors)),
        "flags": sorted(set(flags)),
        "synthetic_results": synthetic_results,
    }


def summarize(items: list[dict[str, Any]], total_available: int) -> dict[str, Any]:
    by_severity = Counter(str(item.get("severity")) for item in items)
    by_type = Counter(str(item.get("evaluator_type")) for item in items)
    by_generation = Counter(str(item.get("generation_method")) for item in items)
    flag_counts: Counter[str] = Counter()
    for item in items:
        flag_counts.update(str(flag) for flag in item.get("flags") or [])
        flag_counts.update("verify_error:" + str(error) for error in item.get("verify_errors") or [])
    audited = len(items)
    clean = by_severity["pass"]
    return {
        "schema_version": "MACCCTUNoiseEvalVerifyReportV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_available": total_available,
        "audited_count": audited,
        "clean_rate": clean / audited if audited else None,
        "by_severity": dict(sorted(by_severity.items())),
        "by_evaluator_type": dict(sorted(by_type.items())),
        "by_generation_method": dict(sorted(by_generation.items())),
        "top_flags": dict(flag_counts.most_common(30)),
    }


def main() -> int:
    args = parse_args()
    artifact_paths = iter_artifact_paths(args.artifact_dir)
    total_available = len(artifact_paths)
    if args.limit is not None and args.limit >= 0 and args.limit < total_available:
        rng = random.Random(args.seed)
        artifact_paths = sorted(rng.sample(artifact_paths, args.limit))

    jobs = [VerifyJob(ordinal=index, artifact_path=path) for index, path in enumerate(artifact_paths, start=1)]
    details = [verify_one(job) for job in jobs]
    summary = summarize(details, total_available=total_available)

    if args.include_passing:
        report_details = details
    else:
        flagged = [item for item in details if item.get("severity") != "pass"]
        report_details = flagged[: max(0, args.max_details)]

    report = {
        **summary,
        "artifact_dir": repo_relative(args.artifact_dir),
        "sample": {
            "limit": args.limit,
            "seed": args.seed,
        },
        "details_truncated": len(report_details) < len([item for item in details if item.get("severity") != "pass"])
        and not args.include_passing,
        "details": report_details,
    }
    write_json(args.output, report)

    print(
        "noise eval verify complete: "
        f"audited={summary['audited_count']}/{summary['total_available']} "
        f"clean_rate={summary['clean_rate']:.3f} "
        f"severity={summary['by_severity']} "
        f"output={repo_relative(args.output)}"
    )
    examples = [item for item in details if item.get("severity") != "pass"][: max(0, args.print_examples)]
    for item in examples:
        print(
            f"- {item.get('severity')} {item.get('node_id')} "
            f"flags={item.get('flags')[:3]} errors={item.get('verify_errors')[:2]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
