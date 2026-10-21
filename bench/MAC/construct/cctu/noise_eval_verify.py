#!/usr/bin/env python3
"""Audit MAC-CCTU noise evaluator artifacts before benchmark grading.

This is a lightweight agent-verification scaffold for the generated
``noise_check_code`` artifacts.  It does not replace human annotation, but it
does separate obviously healthy evaluators from ones worth reviewing by hand.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import random
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.construct.cctu.noise_eval_generation import (  # noqa: E402
    interaction_round_bounds,
    load_env,
    number_after,
    package_specific_tool_calls,
    package_tool_usage,
    package_total_tool_calls,
    parse_llm_json,
    resolve_llm_config,
    tool_like_names_from_text,
    verify_package,
)
from bench.MAC.construct.cctu.noise_eval_grade import evaluate_artifact  # noqa: E402

DEFAULT_ARTIFACT_DIR = Path("bench/MAC/cctu/data/noise_check_code")
DEFAULT_OUTPUT = Path("bench/MAC/cctu/mid_data/eval_step5_5_noise_eval_verify.json")


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
    parser.add_argument("--llm-critic", action="store_true", help="Optionally ask an LLM to review flagged evaluators.")
    parser.add_argument(
        "--llm-critic-limit",
        type=int,
        default=50,
        help="Maximum flagged evaluators to send to the LLM critic. Use -1 for no cap.",
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=1.0)
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
    "length": ("word", "words", "character", "characters", "sentence", "sentences", "length", "paragraph", "paragraphs"),
    "tool_count": ("tool", "tools", "toolset", "tooling", "call", "calls", "invoke", "invocation", "invocations"),
    "tool_usage": ("tool", "tools", "toolset", "tooling", "call", "calls", "invoke", "use", "retriever", "analyzer", "finder", "tracker"),
    "interaction_rounds": ("turn", "turns", "round", "rounds", "interaction", "interactions"),
    "date": ("date", "dates", "year", "month", "day", "timestamp"),
    "punctuation": ("period", "punctuation", "ends", "ending"),
}

FAMILY_FEATURES: dict[str, tuple[str, ...]] = {
    "interaction_rounds": ("interaction_rounds",),
    "parallel_call_count": ("tool_count", "interaction_rounds"),
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


def constraint_requires_positive_markdown(constraint: str, type_hint: list[str]) -> bool:
    lower = constraint.lower()
    if "plain text" in lower or "no markdown" in lower or "without markdown" in lower:
        return False
    return any(token in lower for token in ("markdown", "bold", "heading", "bullet", "emphasis"))


def constraint_requires_length(constraint: str, type_hint: list[str]) -> bool:
    lower = constraint.lower()
    if re.search(
        r"\b(at least|at most|no more than|minimum of|maximum of|under|over|between)\s+[a-z0-9-]+\s+(words?|characters?|sentences?|paragraphs?)\b",
        lower,
    ):
        return True
    if type_hint == ["Response", "Length"]:
        return True
    if re.search(r"\bmulti[- ]paragraph\b", lower) and re.search(r"\b(at least|minimum)\s+[a-z0-9-]+\s+words?\b", lower):
        return True
    normalized = lower.replace("-", " ")
    if "character" in lower and "formatting character" in normalized:
        return False
    return False


def constraint_requires_tool_trace(constraint: str, type_hint: list[str]) -> bool:
    lower = constraint.lower()
    tool_names = tool_like_names_from_text(constraint)
    if package_total_tool_calls(lower):
        return True
    if package_specific_tool_calls(lower, tool_names):
        return True
    if package_tool_usage(lower, tool_names, tool_names):
        return True
    if any(
        token in lower
        for token in (
            "tool call",
            "tool calls",
            "invoke ",
            "invocation",
            "invocations",
            "parallel call",
            "same step",
            "same turn",
            "dry-run",
            "dry run",
            "execution trace",
            "batched into a single interaction turn",
            "rely on",
            "must rely",
        )
    ):
        return True
    if type_hint in (
        ["Resource", "Tool Call Count"],
        ["Resource", "Specific Tool Call Count"],
        ["Behavior", "Sequential Dependencies"],
        ["Behavior", "Parallel Tool Use"],
    ):
        return True
    rounds = interaction_round_bounds(lower)
    tokens = text_tokens(constraint + " " + " ".join(type_hint))
    if rounds.get("max") is not None and "toolset" in tokens:
        return True
    return False


def constraint_requires_interaction_rounds(constraint: str, type_hint: list[str]) -> bool:
    rounds = interaction_round_bounds(constraint.lower())
    return rounds.get("min") is not None or rounds.get("max") is not None


def constraint_forbids_tool_calls(constraint: str) -> bool:
    lower = constraint.lower()
    if re.search(
        r"\b(?:must not|may not|do not|without|never)\s+(?:invoke|call|use)\b|\bforbidden\b|\bavoid calling\b",
        lower,
    ):
        return True
    return bool(
        re.search(
            r"no (?:external )?tool invocations?(?: are permitted| in this phase)?|"
            r"must not include any tool invocations?|"
            r"must not contain tool invocations?|"
            r"without any tool invocations?|"
            r"must not include tool invocations?",
            lower,
        )
    )


def constraint_forbids_all_tool_calls(constraint: str) -> bool:
    return constraint_forbids_tool_calls(constraint)


def constraint_requires_disallowed_tool_counterfactual(constraint: str) -> bool:
    """Whether cf_forbidden_tool_should_fail is meaningful for this constraint."""
    if constraint_forbids_all_tool_calls(constraint):
        return True
    lower = constraint.lower()
    tool_names = tool_like_names_from_text(constraint)
    if not tool_names:
        return False
    if any(token in lower for token in ("only use", "exclusively")):
        return True
    if re.search(r"\blimited to\b.{0,40}\b(?:the|using)\s+[`']?", lower):
        return True
    if re.search(r"\bprefer [`']", lower):
        return True
    if re.search(r"\b(?:restrict|exclusive)\s+(?:outputs|itself|workflow|each|actions)\s+to\b", lower):
        return True
    return False


def constraint_text_mentions_tools(constraint: str) -> bool:
    lower = constraint.lower()
    tool_names = tool_like_names_from_text(constraint)
    if package_total_tool_calls(lower) or package_specific_tool_calls(lower, tool_names):
        return True
    if package_tool_usage(lower, tool_names, tool_names):
        return True
    if tool_names and re.search(
        r"\b(?:must|should|require|every|each|all|treat|mandatory|primary|prioritize|"
        r"cross|at least|calls to|invoked for|invoked with|using the|with the|before being|before recording|before drafting)\b",
        lower,
    ):
        return True
    if len(tool_names) >= 2:
        return True
    return bool(
        re.search(
            r"\b(?:tool calls?|toolset|invoke|invocation|invocations|retriev|must rely|must call|rely on)\b",
            lower,
        )
    )


def constraint_restricts_tool_set(constraint: str) -> bool:
    lower = constraint.lower()
    if constraint_forbids_tool_calls(constraint):
        return True
    if any(token in lower for token in ("only use", "exclusively", "limited to")):
        return True
    return bool(
        re.search(
            r"\b(?:restrict|exclusive).{0,40}\b(?:tool|tools|toolset)\b",
            lower,
        )
    )


def constraint_requires_minimum_tool_calls(constraint: str, type_hint: list[str]) -> bool:
    lower = constraint.lower()
    if constraint_forbids_tool_calls(constraint):
        return False
    total_tool = package_total_tool_calls(lower)
    if total_tool and (total_tool.get("spec") or {}).get("min") is not None:
        return True
    tool_names = tool_like_names_from_text(constraint)
    specific_tool = package_specific_tool_calls(lower, tool_names)
    if specific_tool:
        per_tool = (specific_tool.get("spec") or {}).get("per_tool") or {}
        for bounds in per_tool.values():
            if isinstance(bounds, dict) and bounds.get("min") is not None:
                return True
    tool_usage = package_tool_usage(lower, tool_names, tool_names)
    if tool_usage and (tool_usage.get("spec") or {}).get("required_tools"):
        return True
    if re.search(
        r"\b(?:at least|minimum|must (?:call|invoke|rely)|require).{0,80}\b(?:tool|retriev)",
        lower,
    ):
        return True
    if re.search(r"\bmust use\b", lower) and not re.search(r"\bmust use at most\b", lower):
        if re.search(r"\btool", lower):
            return True
    return False


def mentioned_features(constraint: str, type_hint: list[str]) -> set[str]:
    return {
        feature
        for feature in FEATURE_TERMS
        if feature_mentions_constraint(feature, constraint, type_hint)
    }


def semantic_evaluator_features(constraint: str, type_hint: list[str]) -> set[str]:
    """Feature set aligned with observable constraint semantics, not token noise."""
    features = mentioned_features(constraint, type_hint)
    if "markdown" in features and not constraint_requires_positive_markdown(constraint, type_hint):
        features.discard("markdown")
    if "length" in features and not constraint_requires_length(constraint, type_hint):
        features.discard("length")
    if ("tool_count" in features or "tool_usage" in features) and not constraint_requires_tool_trace(
        constraint, type_hint
    ):
        features.discard("tool_count")
        features.discard("tool_usage")
    if ("tool_count" in features or "tool_usage" in features) and not constraint_text_mentions_tools(constraint):
        lower = constraint.lower()
        tool_names = tool_like_names_from_text(constraint)
        if not (
            package_total_tool_calls(lower)
            or package_specific_tool_calls(lower, tool_names)
            or package_tool_usage(lower, tool_names, tool_names)
        ):
            features.discard("tool_count")
            features.discard("tool_usage")
    if "interaction_rounds" in features and not constraint_requires_interaction_rounds(constraint, type_hint):
        features.discard("interaction_rounds")
    return features


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
    if any(token in lower for token in ("endswith", "end with", "period", "punctuation")):
        features.add("punctuation")
    if "trajectory" in lower or "iteration" in lower:
        features.add("interaction_rounds")
    return features


def expected_evaluator_features(artifact: dict[str, Any]) -> set[str]:
    constraint = str(artifact.get("constraint_text") or "")
    type_hint = [str(item) for item in artifact.get("type_hint") or []]
    return semantic_evaluator_features(constraint, type_hint)


def spec_actual_features(code: str) -> set[str]:
    if "SPEC = " not in code:
        return set()
    spec_line = next((line for line in code.splitlines() if line.strip().startswith("SPEC = ")), "")
    if not spec_line:
        return set()
    features: set[str] = set()
    if "'length'" in spec_line or '"length"' in spec_line or "paragraph_min" in spec_line or "paragraph_max" in spec_line or "sentence_max" in spec_line:
        features.add("length")
    if any(key in spec_line for key in ("tool_call_count", "specific_tool_call_count", "tool_parallel", "require_tool_calls", "tool_usage", "allowed_tools_only", "forbid_tool_calls")):
        features.update({"tool_count", "tool_usage"})
    if "interaction_rounds" in spec_line:
        features.add("interaction_rounds")
    if any(key in spec_line for key in ("json_object", "json_keys_any", "json_only_keys")):
        features.add("json")
    if "requires_bold" in spec_line or "markdown_any" in spec_line:
        features.add("markdown")
    if "date_format" in spec_line:
        features.add("date")
    if "no_trailing_punctuation" in spec_line or (
        "response_checks" in spec_line and "ends_with" in spec_line and ("'.'" in spec_line or '"."' in spec_line)
    ):
        features.add("punctuation")
    return features


def actual_evaluator_features(artifact: dict[str, Any], code: str | None) -> set[str]:
    evaluator = artifact.get("evaluator") if isinstance(artifact.get("evaluator"), dict) else {}
    evaluator_type = str(evaluator.get("evaluator_type") or "")
    if evaluator_type == "structured":
        return set(FAMILY_FEATURES.get(str(evaluator.get("family") or ""), ()))
    if evaluator_type == "python" and code:
        if "SPEC = " in code:
            return spec_actual_features(code)
        return detect_code_features(code)
    return set()


def coverage_flags(artifact: dict[str, Any], code: str | None) -> list[str]:
    expected = expected_evaluator_features(artifact)
    actual = actual_evaluator_features(artifact, code)
    missing = sorted(expected - actual)
    flags = [f"coverage_missing:{feature}" for feature in missing]
    if len(expected) >= 2 and missing:
        flags.append("possible_composite_constraint_partially_covered")
    if code and "observable behavior matched minimal check" in code and (missing or len(expected) >= 2):
        flags.append("possible_minimal_template_undercoverage")
    return flags


def ast_complexity_flags(code: str) -> list[str]:
    if "SPEC = " in code and "def evaluate(trace):" in code:
        return []
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

    if "SPEC = " in code and "def evaluate(trace):" in code:
        return sorted(set(flags))

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
    uses_tool_trace = "tool_calls" in lower_code or "trajectory" in lower_code
    if uses_tool_trace and not constraint_requires_tool_trace(constraint, type_hint):
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


def extract_tool_names(text: str) -> list[str]:
    names = sorted(set(re.findall(r"\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b", text)))
    return names


def long_text(word_count: int) -> str:
    return " ".join(f"word{i}" for i in range(word_count))


def feature_counterfactual_traces(artifact: dict[str, Any]) -> list[tuple[str, dict[str, Any], bool]]:
    """Return simple feature-targeted traces with their expected observed value.

    These cases intentionally test broad evaluator alignment, not task answer
    correctness.  They are conservative: a case is only added when the
    constraint text clearly mentions the corresponding feature.
    """
    constraint = str(artifact.get("constraint_text") or "")
    lower = constraint.lower()
    expected = expected_evaluator_features(artifact)
    traces: list[tuple[str, dict[str, Any], bool]] = []
    base = {"trajectory": [], "tool_calls": []}

    if "markdown" in expected:
        traces.append(("cf_markdown_plain_should_fail", {**base, "final_response": "The answer is 2020-01-01."}, False))
    if "json" in expected:
        traces.append(("cf_json_plain_should_fail", {**base, "final_response": "The answer is Paris."}, False))
    if "date" in expected:
        traces.append(("cf_date_missing_should_fail", {**base, "final_response": "The answer is unknown."}, False))
    if "punctuation" in expected and ("period" in lower or " end " in f" {lower} ") and "no trailing punctuation" not in lower:
        traces.append(("cf_period_missing_should_fail", {**base, "final_response": "The answer is Paris"}, False))
    if "length" in expected:
        min_words = number_after(
            lower,
            [
                r"(?:at least|minimum of|min(?:imum)?|no fewer than)\s+([a-z0-9-]+)\s+words",
                r"(?:multi-paragraph|multi paragraph).{0,40}?at least\s+([a-z0-9-]+)\s+words",
            ],
        )
        if min_words is not None and min_words > 2:
            traces.append(("cf_short_response_should_fail", {**base, "final_response": "short answer"}, False))

    tool_names = extract_tool_names(constraint)
    type_hint = [str(item) for item in artifact.get("type_hint") or []]
    if ("tool_usage" in expected or "tool_count" in expected) and constraint_requires_minimum_tool_calls(
        constraint, type_hint
    ):
        traces.append(("cf_no_tool_calls_should_fail", {**base, "final_response": long_text(450)}, False))
    if ("tool_usage" in expected or "tool_count" in expected) and constraint_requires_disallowed_tool_counterfactual(
        constraint
    ):
        traces.append(
            (
                "cf_forbidden_tool_should_fail",
                {
                    "final_response": long_text(450),
                    "trajectory": [],
                    "tool_calls": [{"index": 0, "iteration": 1, "name": "forbidden_tool", "arguments": {}, "result": "x"}],
                },
                False,
            )
        )
    if tool_names and constraint_requires_minimum_tool_calls(constraint, type_hint):
            traces.append(
                (
                    "cf_named_tool_present_smoke",
                    {
                        "final_response": long_text(450),
                        "trajectory": [],
                        "tool_calls": [
                            {"index": index, "iteration": 1, "name": name, "arguments": {}, "result": "x"}
                            for index, name in enumerate(tool_names[:3])
                        ],
                    },
                    True,
                )
            )
    if "interaction_rounds" in expected and re.search(r"\bat most\s+\d+|\bno more than\s+\d+|\bnot exceed", lower):
        traces.append(
            (
                "cf_many_interaction_turns_should_fail",
                {
                    "final_response": long_text(50),
                    "trajectory": [{"iteration": index, "tool_calls": []} for index in range(1, 8)],
                    "tool_calls": [],
                },
                False,
            )
        )
    return traces


def run_counterfactual_cases(
    artifact: dict[str, Any],
    code_path: Path | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    unit = {"code_path": repo_relative(code_path)} if code_path is not None else {}
    results: list[dict[str, Any]] = []
    flags: list[str] = []
    for name, trace, expected_observed in feature_counterfactual_traces(artifact):
        result = evaluate_artifact(artifact, unit, trace)
        observed = result.get("observed_followed")
        results.append(
            {
                "case": name,
                "expected_observed": expected_observed,
                "observed_followed": observed if observed in {True, False, None} else None,
                "confidence": result.get("confidence"),
                "reason": result.get("reason"),
            }
        )
        if observed is True and expected_observed is False:
            flags.append(name.replace("cf_", "counterfactual_") + "_passed")
    return results, sorted(set(flags))


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


def build_llm_critic_prompt(item: dict[str, Any], code: str | None) -> str:
    payload = {
        "task": (
            "Review whether this evaluator checks the constraint too loosely, too strictly, "
            "or includes unrelated logic. Focus on semantic alignment, not answer correctness."
        ),
        "constraint_text": item.get("constraint_text"),
        "type_hint": item.get("type_hint"),
        "expected_should_apply": item.get("expected_should_apply"),
        "is_anchor": item.get("is_anchor"),
        "evaluator_type": item.get("evaluator_type"),
        "static_flags": item.get("flags"),
        "verify_errors": item.get("verify_errors"),
        "synthetic_results": item.get("synthetic_results"),
        "counterfactual_results": item.get("counterfactual_results"),
        "code": (code or "")[:6000],
        "response_schema": {
            "severity": "pass|review|needs_human",
            "flags": ["short snake_case issue labels"],
            "summary": "one sentence",
            "suggested_fix": "one sentence or empty string",
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def call_critic_llm(
    *,
    args: argparse.Namespace,
    prompt: str,
) -> dict[str, Any]:
    try:
        openai_module = importlib.import_module("openai")
    except ImportError as exc:
        raise RuntimeError("openai package is required for --llm-critic") from exc
    if not args.model:
        raise ValueError("Missing model. Pass --model or set LLM_MODEL.")
    if not args.api_key:
        raise ValueError("Missing API key. Pass --api-key or set LLM_API_KEY.")
    client = openai_module.OpenAI(api_key=args.api_key, base_url=args.base_url or None, timeout=args.timeout, max_retries=0)
    last_error: Exception | None = None
    for attempt in range(1, max(1, args.retries) + 1):
        try:
            response = client.chat.completions.create(
                model=args.model,
                temperature=0.0,
                max_tokens=args.max_tokens,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are auditing generated benchmark evaluators. "
                            "Return strict JSON only. Do not use Markdown."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            parsed = parse_llm_json(response.choices[0].message.content or "")
            severity_value = str(parsed.get("severity") or "review")
            if severity_value not in {"pass", "review", "needs_human"}:
                parsed["severity"] = "review"
            parsed["flags"] = [str(flag) for flag in parsed.get("flags") or []]
            parsed["summary"] = str(parsed.get("summary") or "")
            parsed["suggested_fix"] = str(parsed.get("suggested_fix") or "")
            return parsed
        except Exception as exc:  # noqa: BLE001 - provider or JSON errors are retried.
            last_error = exc
            if attempt == max(1, args.retries):
                break
            time.sleep(args.sleep * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM critic failed after {args.retries} attempts: {last_error}") from last_error


def severity(flags: list[str], verify_errors: list[str]) -> str:
    if verify_errors:
        return "fail"
    hard_prefixes = ("synthetic_", "counterfactual_", "possible_json_checker_contains_length")
    if any(flag.startswith(hard_prefixes) for flag in flags):
        return "needs_human"
    if any(flag.startswith("coverage_missing:") or flag == "possible_minimal_template_undercoverage" for flag in flags):
        return "coverage_review"
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

    expected_features = expected_evaluator_features(artifact)
    actual_features = actual_evaluator_features(artifact, code)
    missing_features = sorted(expected_features - actual_features)

    flags = static_flags(artifact, code)
    flags.extend(coverage_flags(artifact, code))
    synthetic_results: list[dict[str, Any]] = []
    counterfactual_results: list[dict[str, Any]] = []
    if evaluator.get("status") == "success" and not verify_errors:
        synthetic_results, synthetic_flags = run_synthetic_cases(artifact, code_path)
        flags.extend(synthetic_flags)
        counterfactual_results, counterfactual_flags = run_counterfactual_cases(artifact, code_path)
        flags.extend(counterfactual_flags)

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
        "expected_features": sorted(expected_features),
        "actual_features": sorted(actual_features),
        "missing_features": missing_features,
        "verify_errors": sorted(set(verify_errors)),
        "flags": sorted(set(flags)),
        "synthetic_results": synthetic_results,
        "counterfactual_results": counterfactual_results,
    }


def apply_llm_critic(details: list[dict[str, Any]], args: argparse.Namespace) -> int:
    flagged = [item for item in details if item.get("severity") != "pass"]
    if args.llm_critic_limit is not None and args.llm_critic_limit >= 0:
        flagged = flagged[: args.llm_critic_limit]
    if not flagged:
        return 0

    load_env(args.env_file)
    resolve_llm_config(args)
    reviewed = 0
    for item in flagged:
        code = None
        code_path = item.get("code_path")
        if isinstance(code_path, str) and code_path:
            resolved = resolve_path(Path(code_path))
            if resolved.exists():
                code = resolved.read_text(encoding="utf-8")
        try:
            result = call_critic_llm(args=args, prompt=build_llm_critic_prompt(item, code))
        except Exception as exc:  # noqa: BLE001 - one critic failure should not abort deterministic verification.
            result = {
                "severity": "review",
                "flags": ["llm_critic_failed"],
                "summary": f"LLM critic failed: {type(exc).__name__}: {exc}",
                "suggested_fix": "",
            }
        item["llm_critic"] = result
        reviewed += 1
        critic_flags = [f"llm_critic:{flag}" for flag in result.get("flags") or []]
        item["flags"] = sorted(set([*(item.get("flags") or []), *critic_flags]))
        critic_severity = str(result.get("severity") or "")
        if critic_severity == "needs_human":
            item["severity"] = "needs_human"
        elif critic_severity == "review" and item.get("severity") == "pass":
            item["severity"] = "review"
    return reviewed


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
    llm_reviewed_count = apply_llm_critic(details, args) if args.llm_critic else 0
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
        "llm_critic": {
            "enabled": bool(args.llm_critic),
            "reviewed_count": llm_reviewed_count,
            "limit": args.llm_critic_limit,
            "model": args.model if args.llm_critic else None,
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
