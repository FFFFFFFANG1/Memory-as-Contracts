"""Optional fuzzy hints for CCTU tool simulators."""

from __future__ import annotations

import json
import os
import re
from typing import Any

_FAILURE_MARKERS = (
    "not found",
    "no successor",
    "no historical event",
    "no information found",
    "no event",
    "error:",
)

_TUPLE_KEY_RE = re.compile(
    r"\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*:",
)
_STRING_EQ_RE = re.compile(
    r"(\w+)\.lower\(\)\s*==\s*['\"]([^'\"]+)['\"]",
    flags=re.IGNORECASE,
)
_DEF_RE = re.compile(r"def\s+\w+\s*\(([^)]*)\)", flags=re.DOTALL)

DEFAULT_MATCH_MODE = "exact"
DEFAULT_MIN_SCORE = 0.35
DEFAULT_MAX_SUGGESTIONS = 2


def cctu_tool_match_mode() -> str:
    return os.environ.get("CCTU_TOOL_MATCH_MODE", DEFAULT_MATCH_MODE).strip().lower()


def cctu_tool_match_min_score() -> float:
    raw = os.environ.get("CCTU_TOOL_MATCH_MIN_SCORE", str(DEFAULT_MIN_SCORE)).strip()
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_MIN_SCORE


def normalize_match_text(text: Any) -> str:
    text = str(text or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_cctu_arguments(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    args = dict(arguments)
    role = args.get("role")
    figure_key = None
    for key in ("political_figure", "figure", "leader_name", "person_name"):
        if key in args:
            figure_key = key
            break
    if role and figure_key:
        figure = str(args.get(figure_key) or "")
        role_text = str(role)
        if role_text and normalize_match_text(role_text) not in normalize_match_text(figure):
            args[figure_key] = f"{role_text} {figure}".strip()
    return args


def is_failure_result(result: str) -> bool:
    lower = result.lower()
    return any(marker in lower for marker in _FAILURE_MARKERS)


def _parse_param_names(code: str) -> list[str]:
    match = _DEF_RE.search(code)
    if not match:
        return []
    params: list[str] = []
    for part in match.group(1).split(","):
        token = part.strip()
        if not token or token.startswith("*"):
            continue
        name = token.split("=")[0].strip()
        if name:
            params.append(name)
    return params


def _extract_string_equality_goldens(code: str) -> list[dict[str, str]]:
    goldens: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for param, value in _STRING_EQ_RE.findall(code):
        key = (param, value)
        if key in seen:
            continue
        seen.add(key)
        goldens.append({param: value})
    return goldens


def _extract_tuple_goldens(code: str, param_names: list[str]) -> list[dict[str, str]]:
    if len(param_names) < 3:
        return []
    goldens: list[dict[str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for match in _TUPLE_KEY_RE.finditer(code):
        values = match.groups()
        if values in seen:
            continue
        seen.add(values)
        goldens.append(
            {
                param_names[0]: values[0],
                param_names[1]: values[1],
                param_names[2]: values[2],
            }
        )
    return goldens


def extract_golden_inputs(code: str) -> list[dict[str, str]]:
    param_names = _parse_param_names(code)
    goldens = _extract_string_equality_goldens(code)
    goldens.extend(_extract_tuple_goldens(code, param_names))
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for golden in goldens:
        key = json.dumps(golden, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(golden)
    return deduped


def _text_similarity(left: Any, right: Any) -> float:
    left_norm = normalize_match_text(left)
    right_norm = normalize_match_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    if left_norm in right_norm or right_norm in left_norm:
        return 0.85
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    coverage = overlap / len(right_tokens)
    precision = overlap / len(left_tokens)
    return 0.5 * coverage + 0.5 * precision


def score_golden_arguments(query_args: dict[str, Any], golden: dict[str, str]) -> float:
    if not golden:
        return 0.0
    scores: list[float] = []
    for key, golden_value in golden.items():
        if key not in query_args:
            continue
        scores.append(_text_similarity(query_args.get(key), golden_value))
    if scores:
        return sum(scores) / len(scores)

    query_chunks = [str(value) for value in query_args.values() if str(value).strip()]
    golden_chunks = [str(value) for value in golden.values() if str(value).strip()]
    if not query_chunks or not golden_chunks:
        return 0.0
    query_text = " ".join(query_chunks)
    golden_text = " ".join(golden_chunks)
    return _text_similarity(query_text, golden_text)


def format_suggestion(golden: dict[str, str]) -> str:
    if len(golden) == 1:
        key, value = next(iter(golden.items()))
        return f"{key}={value!r}"
    parts = [f"{key}={value!r}" for key, value in golden.items()]
    return ", ".join(parts)


def format_did_you_mean(failure: str, suggestions: list[str]) -> str:
    if not suggestions:
        return failure
    base = failure.rstrip()
    if len(suggestions) == 1:
        return f"{base} Did you mean {suggestions[0]} instead?"
    first, second = suggestions[0], suggestions[1]
    return f"{base} Did you mean {first} or {second} instead?"


def rank_golden_suggestions(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    min_score: float = DEFAULT_MIN_SCORE,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
) -> list[str]:
    query_args = normalize_cctu_arguments(tool_name, arguments)
    ranked: list[tuple[float, dict[str, str]]] = []
    for golden in extract_golden_inputs(code):
        score = score_golden_arguments(query_args, golden)
        if score >= min_score:
            ranked.append((score, golden))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [format_suggestion(golden) for _, golden in ranked[:max(0, max_suggestions)]]


def maybe_append_did_you_mean(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    result: str,
    min_score: float | None = None,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
) -> str:
    if not is_failure_result(result):
        return result
    threshold = DEFAULT_MIN_SCORE if min_score is None else min_score
    suggestions = rank_golden_suggestions(
        tool_name=tool_name,
        arguments=arguments,
        code=code,
        min_score=threshold,
        max_suggestions=max_suggestions,
    )
    return format_did_you_mean(result, suggestions)


def cctu_call_function_with_match_mode(
    name: str,
    arguments: dict[str, Any],
    code: str,
    *,
    match_mode: str | None = None,
    call_function: Any,
) -> str:
    mode = (match_mode or cctu_tool_match_mode()).strip().lower()
    result = call_function(name, arguments, code)
    if mode != "suggest":
        return result
    return maybe_append_did_you_mean(
        tool_name=name,
        arguments=arguments,
        code=code,
        result=result,
        min_score=cctu_tool_match_min_score(),
    )
