"""Optional fuzzy hints for CCTU tool simulators."""

from __future__ import annotations

import json
import os
import re
import ast
from typing import Any, Callable

_FAILURE_MARKERS = (
    "not found",
    "no successor",
    "no historical event",
    "no information found",
    "no event",
    "error occured",
    "error occurred",
    "error:",
)

_STUB_MARKERS = (
    "retrieved successfully",
    "information retrieved successfully",
)

_NON_DIRECT_MATCH_ERROR = '{"error": "No exact match for the given parameters."}'

_TUPLE_KEY_RE = re.compile(
    r"\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*:",
)
_TUPLE_DICT_KEY_RE = re.compile(
    r"\(\s*((?:['\"][^'\"]*['\"]|(?:\d+\.?\d*))\s*(?:,\s*(?:['\"][^'\"]*['\"]|(?:\d+\.?\d*)))*)\s*\)\s*:",
)
_COMPOSITE_KEY_IN_RE = re.compile(
    r"\(\s*(\w+(?:\s*,\s*\w+)+)\s*\)\s+in\s+(\w+)\b",
)
_KEY_TUPLE_ASSIGN_RE = re.compile(
    r"(\w+)\s*=\s*\(\s*(\w+(?:\s*,\s*\w+)+)\s*\)",
)
_KEY_VAR_IN_DICT_RE = re.compile(r"(\w+)\s+in\s+(\w+)\b")
_LIST_ASSIGN_RE = re.compile(r"^\s*(\w+)\s*=\s*\[", re.MULTILINE)
_FOR_LOOP_RE = re.compile(r"for\s+(\w+)\s+in\s+(\w+)\s*:")
_LOOP_BRACKET_EQ_RE = re.compile(
    r"(\w+)\[['\"](\w+)['\"]\]\s*==\s*(\w+)\b",
)
_LOOP_GET_EQ_RE = re.compile(
    r"(\w+)\.get\(['\"](\w+)['\"](?:,\s*[^)]+)?\)\s*==\s*(\w+)\b",
)
_FIELD_VALUE_RE = re.compile(
    r"['\"](\w+)['\"]\s*:\s*(?:['\"]([^'\"]*)['\"]|(\d+))",
)
_NUMERIC_PARAMS = frozenset(
    {
        "year",
        "count",
        "duration",
        "election_year",
        "month",
        "day",
        "elevation",
        "age",
        "quantity",
    },
)
_STRING_EQ_RE = re.compile(
    r"(\w+)\.lower\(\)\s*==\s*['\"]([^'\"]+)['\"]",
    flags=re.IGNORECASE,
)
_DIRECT_EQ_RE = re.compile(
    r"(\w+)\s*==\s*['\"]([^'\"]+)['\"]",
    flags=re.IGNORECASE,
)
_IF_ELIF_LINE_RE = re.compile(r"^\s*(?:if|elif)\s+(.+?):", re.MULTILINE)
_DICT_ASSIGN_RE = re.compile(r"^\s*(\w+)\s*=\s*\{", re.MULTILINE)
_DICT_KEY_AT_DEPTH_ONE_RE = re.compile(r"['\"]([^'\"]+)['\"]\s*:")
_DICT_GET_LOOKUP_RE = re.compile(r"(\w+)\.get\(\s*(\w+)\s*\)")
_DICT_BRACKET_LOOKUP_RE = re.compile(r"(\w+)\[\s*(\w+)\s*\]")
_DICT_IN_LOOKUP_RE = re.compile(r"(\w+)\s+in\s+(\w+)\b")
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
    lower = result.lower().strip()
    if lower.startswith("{") and '"error"' in lower:
        return True
    if lower.startswith("{") and "'error'" in lower:
        return True
    return any(marker in lower for marker in _FAILURE_MARKERS)


def is_stub_result(result: str) -> bool:
    lower = result.lower().strip()
    if any(marker in lower for marker in _STUB_MARKERS):
        return True
    if not lower.startswith("{"):
        return False
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict) or "error" in payload:
        return False
    if "result" in payload:
        return False
    if "message" in payload:
        return True
    return False


def _values_equal(query_value: Any, golden_value: str) -> bool:
    if isinstance(query_value, (dict, list)):
        encoded = json.dumps(query_value, ensure_ascii=False, sort_keys=True)
        return normalize_match_text(encoded) == normalize_match_text(golden_value)
    return normalize_match_text(query_value) == normalize_match_text(golden_value)


def arguments_match_golden(query_args: dict[str, Any], golden: dict[str, str]) -> bool:
    if not golden:
        return False
    for key, golden_value in golden.items():
        query_value = _get_argument_path(query_args, key)
        if query_value is None:
            return False
        if not _values_equal(query_value, golden_value):
            return False
    return True


def is_direct_hit(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    result: str,
) -> bool:
    if is_failure_result(result) or is_stub_result(result):
        return False
    goldens = extract_golden_inputs(code)
    if not goldens:
        return True
    query_args = normalize_cctu_arguments(tool_name, arguments)
    max_len = max(len(golden) for golden in goldens)
    for golden in goldens:
        if len(golden) < max_len:
            continue
        if arguments_match_golden(query_args, golden):
            return True
    return False


def non_direct_match_failure(result: str) -> str:
    if is_failure_result(result):
        return result
    return _NON_DIRECT_MATCH_ERROR


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


def _find_matching_close(code: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    for index in range(start, len(code)):
        char = code[index]
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return len(code) - 1


def _split_csv_idents(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _parse_tuple_key_values(inner: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"['\"]([^'\"]*)['\"]|(\d+)", inner):
        values.append(match.group(1) if match.group(1) is not None else match.group(2))
    return values


def _parse_tuple_dict_keys(code: str) -> dict[str, list[list[str]]]:
    dict_tuples: dict[str, list[list[str]]] = {}
    for match in _DICT_ASSIGN_RE.finditer(code):
        var_name = match.group(1)
        block_end = _find_matching_close(code, match.end() - 1, "{", "}")
        block = code[match.end() - 1 : block_end + 1]
        tuples: list[list[str]] = []
        for tuple_match in _TUPLE_DICT_KEY_RE.finditer(block):
            values = _parse_tuple_key_values(tuple_match.group(1))
            if len(values) >= 2:
                tuples.append(values)
        if tuples:
            existing = dict_tuples.setdefault(var_name, [])
            for item in tuples:
                if item not in existing:
                    existing.append(item)
    return dict_tuples


def _parse_composite_lookup_params(code: str) -> list[tuple[str, list[str]]]:
    lookups: list[tuple[str, list[str]]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    def add_lookup(dict_name: str, params: list[str]) -> None:
        key = (dict_name, tuple(params))
        if key in seen:
            return
        seen.add(key)
        lookups.append((dict_name, params))

    for match in _COMPOSITE_KEY_IN_RE.finditer(code):
        add_lookup(match.group(2), _split_csv_idents(match.group(1)))

    for match in _KEY_TUPLE_ASSIGN_RE.finditer(code):
        key_var = match.group(1)
        params = _split_csv_idents(match.group(2))
        for in_match in _KEY_VAR_IN_DICT_RE.finditer(code):
            if in_match.group(1) != key_var:
                continue
            add_lookup(in_match.group(2), params)
    return lookups


def _extract_tuple_goldens(code: str, param_names: list[str]) -> list[dict[str, str]]:
    goldens: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_golden(golden: dict[str, str]) -> None:
        key = json.dumps(golden, sort_keys=True, ensure_ascii=False)
        if key in seen:
            return
        seen.add(key)
        goldens.append(golden)

    dict_tuples = _parse_tuple_dict_keys(code)
    for dict_name, params in _parse_composite_lookup_params(code):
        for values in dict_tuples.get(dict_name, []):
            if len(values) != len(params):
                continue
            add_golden({params[index]: values[index] for index in range(len(params))})

    if len(param_names) >= 3:
        for match in _TUPLE_KEY_RE.finditer(code):
            values = match.groups()
            add_golden(
                {
                    param_names[0]: values[0],
                    param_names[1]: values[1],
                    param_names[2]: values[2],
                }
            )
    return goldens


def _flatten_literal_fields(value: Any, *, prefix: str = "") -> dict[str, str]:
    fields: dict[str, str] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if isinstance(item, dict):
                fields.update(_flatten_literal_fields(item, prefix=path))
            elif isinstance(item, (str, int, float)):
                fields[path] = str(item)
                if "." in path:
                    fields.setdefault(key_text, str(item))
        return fields
    return fields


def _parse_simple_dict_fields(dict_code: str) -> dict[str, str]:
    try:
        value = ast.literal_eval(dict_code)
    except (SyntaxError, ValueError):
        value = None
    if isinstance(value, dict):
        return _flatten_literal_fields(value)

    fields: dict[str, str] = {}
    for match in _FIELD_VALUE_RE.finditer(dict_code):
        value = match.group(2)
        if value is None:
            value = match.group(3)
        if value is not None:
            fields[match.group(1)] = value
    return fields


def _extract_list_of_dict_records(code: str, bracket_pos: int) -> list[dict[str, str]]:
    close = _find_matching_close(code, bracket_pos, "[", "]")
    segment = code[bracket_pos : close + 1]
    records: list[dict[str, str]] = []
    index = 1
    while index < len(segment) - 1:
        if segment[index] == "{":
            dict_close = _find_matching_close(segment, index, "{", "}")
            fields = _parse_simple_dict_fields(segment[index : dict_close + 1])
            if fields:
                records.append(fields)
            index = dict_close + 1
            continue
        index += 1
    return records


def _parse_list_records(code: str) -> dict[str, list[dict[str, str]]]:
    list_records: dict[str, list[dict[str, str]]] = {}
    for match in _LIST_ASSIGN_RE.finditer(code):
        records = _extract_list_of_dict_records(code, match.end() - 1)
        if not records:
            continue
        var_name = match.group(1)
        existing = list_records.setdefault(var_name, [])
        for record in records:
            if record not in existing:
                existing.append(record)
    return list_records


def _expr_root_path(node: ast.AST) -> tuple[str, tuple[str, ...]] | None:
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"lower", "strip"} and not node.args:
            return _expr_root_path(node.func.value)
        if isinstance(node.func, ast.Name) and node.func.id in {"str", "int", "float"} and len(node.args) == 1:
            return _expr_root_path(node.args[0])
        return None

    if isinstance(node, ast.Attribute):
        value = _expr_root_path(node.value)
        if value is None:
            return None
        root, path = value
        return root, (*path, node.attr)

    if isinstance(node, ast.Subscript):
        value = _expr_root_path(node.value)
        if value is None:
            return None
        key_node = node.slice
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, (str, int)):
            key = str(key_node.value)
        else:
            return None
        root, path = value
        return root, (*path, key)

    if isinstance(node, ast.Name):
        return node.id, ()

    return None


def _compare_field_param_pairs(node: ast.AST, *, loop_var: str, param_names: set[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if isinstance(node, ast.BoolOp):
        for value in node.values:
            pairs.extend(_compare_field_param_pairs(value, loop_var=loop_var, param_names=param_names))
        return pairs
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
        return pairs
    if len(node.comparators) != 1:
        return pairs

    left = _expr_root_path(node.left)
    right = _expr_root_path(node.comparators[0])
    if left is None or right is None:
        return pairs

    for field_side, param_side in ((left, right), (right, left)):
        field_root, field_path = field_side
        param_root, param_path = param_side
        if field_root != loop_var or not field_path or param_root not in param_names:
            continue
        field = ".".join(field_path)
        param = ".".join((param_root, *param_path))
        pairs.append((field, param))
    return pairs


def _parse_ast_loop_field_param_maps(code: str) -> dict[str, list[tuple[str, str]]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}

    param_names = set(_parse_param_names(code))
    maps: dict[str, list[tuple[str, str]]] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.For) or not isinstance(node.target, ast.Name):
            continue
        if not isinstance(node.iter, ast.Name):
            continue
        loop_var = node.target.id
        list_var = node.iter.id
        pairs: list[tuple[str, str]] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.If):
                continue
            for pair in _compare_field_param_pairs(child.test, loop_var=loop_var, param_names=param_names):
                if pair not in pairs:
                    pairs.append(pair)
        if not pairs:
            continue
        existing = maps.setdefault(list_var, [])
        for pair in pairs:
            if pair not in existing:
                existing.append(pair)
    return maps


def _parse_loop_field_param_maps(code: str) -> dict[str, list[tuple[str, str]]]:
    maps: dict[str, list[tuple[str, str]]] = {}
    for match in _FOR_LOOP_RE.finditer(code):
        loop_var, list_var = match.group(1), match.group(2)
        chunk = code[match.end() : match.end() + 2500]
        pairs: list[tuple[str, str]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for loop_item, field, param in _LOOP_BRACKET_EQ_RE.findall(chunk):
            if loop_item != loop_var:
                continue
            pair = (field, param)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            pairs.append(pair)
        for loop_item, field, param in _LOOP_GET_EQ_RE.findall(chunk):
            if loop_item != loop_var:
                continue
            pair = (field, param)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            pairs.append(pair)
        if pairs:
            existing = maps.setdefault(list_var, [])
            for pair in pairs:
                if pair not in existing:
                    existing.append(pair)
    ast_maps = _parse_ast_loop_field_param_maps(code)
    for list_var, pairs in ast_maps.items():
        existing = maps.setdefault(list_var, [])
        for pair in pairs:
            if pair not in existing:
                existing.append(pair)
    return maps


def _extract_for_loop_goldens(code: str) -> list[dict[str, str]]:
    list_records = _parse_list_records(code)
    field_maps = _parse_loop_field_param_maps(code)
    goldens: list[dict[str, str]] = []
    seen: set[str] = set()
    for list_var, mappings in field_maps.items():
        records = list_records.get(list_var, [])
        if not records:
            continue
        for record in records:
            golden: dict[str, str] = {}
            for field, param in mappings:
                value = record.get(field)
                if value is None:
                    continue
                golden[param] = value
            if not golden:
                continue
            key = json.dumps(golden, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            goldens.append(golden)
    return goldens


def _extract_top_level_dict_keys(code: str, open_brace_pos: int) -> list[str]:
    keys: list[str] = []
    depth = 0
    index = open_brace_pos
    length = len(code)
    while index < length:
        char = code[index]
        if char == "{":
            depth += 1
            index += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                break
            index += 1
            continue
        if depth == 1:
            match = _DICT_KEY_AT_DEPTH_ONE_RE.match(code, index)
            if match:
                keys.append(match.group(1))
                index = match.end()
                continue
        index += 1
    return keys


def _parse_lookup_dict_keys(code: str) -> dict[str, list[str]]:
    dict_keys: dict[str, list[str]] = {}
    for match in _DICT_ASSIGN_RE.finditer(code):
        var_name = match.group(1)
        keys = _extract_top_level_dict_keys(code, match.end() - 1)
        if not keys:
            continue
        existing = dict_keys.setdefault(var_name, [])
        for key in keys:
            if key not in existing:
                existing.append(key)
    return dict_keys


def _parse_dict_lookup_params(code: str, dict_names: set[str]) -> dict[str, set[str]]:
    lookup_params: dict[str, set[str]] = {}
    for dict_name, param in _DICT_GET_LOOKUP_RE.findall(code):
        if dict_name not in dict_names:
            continue
        lookup_params.setdefault(dict_name, set()).add(param)
    for dict_name, param in _DICT_BRACKET_LOOKUP_RE.findall(code):
        if dict_name not in dict_names:
            continue
        lookup_params.setdefault(dict_name, set()).add(param)
    for param, dict_name in _DICT_IN_LOOKUP_RE.findall(code):
        if param == "not" or dict_name not in dict_names:
            continue
        lookup_params.setdefault(dict_name, set()).add(param)
    return lookup_params


def _extract_dict_lookup_goldens(code: str) -> list[dict[str, str]]:
    dict_keys = _parse_lookup_dict_keys(code)
    if not dict_keys:
        return []
    lookup_params = _parse_dict_lookup_params(code, set(dict_keys))
    goldens: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for dict_name, params in lookup_params.items():
        keys = dict_keys.get(dict_name)
        if not keys:
            continue
        for param in params:
            for key in keys:
                dedupe_key = (param, key)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                goldens.append({param: key})
    return goldens


def _direct_equality_pairs(condition: str) -> list[tuple[str, str]]:
    if ".lower()" in condition:
        return []
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for param, value in _DIRECT_EQ_RE.findall(condition):
        key = (param, value)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    return pairs


def _extract_direct_equality_goldens(code: str) -> list[dict[str, str]]:
    goldens: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_golden(golden: dict[str, str]) -> None:
        key = json.dumps(golden, sort_keys=True, ensure_ascii=False)
        if key in seen:
            return
        seen.add(key)
        goldens.append(golden)

    for match in _IF_ELIF_LINE_RE.finditer(code):
        pairs = _direct_equality_pairs(match.group(1))
        if not pairs:
            continue
        for param, value in pairs:
            add_golden({param: value})
        if len(pairs) > 1:
            add_golden(dict(pairs))
    return goldens


def _dedupe_goldens(goldens: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for golden in goldens:
        key = json.dumps(golden, sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(golden)
    return deduped


def extract_golden_inputs(code: str) -> list[dict[str, str]]:
    param_names = _parse_param_names(code)
    goldens = _extract_string_equality_goldens(code)
    goldens.extend(_extract_tuple_goldens(code, param_names))
    goldens.extend(_extract_direct_equality_goldens(code))
    goldens.extend(_extract_dict_lookup_goldens(code))
    goldens.extend(_extract_for_loop_goldens(code))
    return _dedupe_goldens(goldens)


def _coerce_golden_value(param: str, value: str, arguments: dict[str, Any]) -> Any:
    existing = _get_argument_path(arguments, param)
    if isinstance(existing, bool):
        return value
    if isinstance(existing, int):
        try:
            return int(value)
        except (ValueError, TypeError):
            return value
    if isinstance(existing, float):
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    if param in _NUMERIC_PARAMS and str(value).isdigit():
        return int(value)
    return value


def _get_argument_path(arguments: dict[str, Any], path: str) -> Any:
    current: Any = arguments
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_argument_path(arguments: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current: dict[str, Any] = arguments
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


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
        query_value = _get_argument_path(query_args, key)
        if query_value is None:
            continue
        scores.append(_text_similarity(query_value, golden_value))
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


def merge_golden_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    golden: dict[str, str],
) -> dict[str, Any]:
    merged = dict(arguments)
    for key, value in golden.items():
        _set_argument_path(merged, key, _coerce_golden_value(key, value, arguments))
    return normalize_cctu_arguments(tool_name, merged)


def rank_golden_candidates(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    min_score: float = DEFAULT_MIN_SCORE,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
) -> list[dict[str, str]]:
    query_args = normalize_cctu_arguments(tool_name, arguments)
    ranked: list[tuple[float, dict[str, str]]] = []
    for golden in extract_golden_inputs(code):
        score = score_golden_arguments(query_args, golden)
        if score >= min_score:
            ranked.append((score, golden))
    ranked.sort(key=lambda item: (len(item[1]), item[0]), reverse=True)
    return [golden for _, golden in ranked[:max(0, max_suggestions)]]


def rank_golden_suggestions(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    min_score: float = DEFAULT_MIN_SCORE,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
) -> list[str]:
    return [
        format_suggestion(golden)
        for golden in rank_golden_candidates(
            tool_name=tool_name,
            arguments=arguments,
            code=code,
            min_score=min_score,
            max_suggestions=max_suggestions,
        )
    ]


def format_similar_parameter_results(
    original: str,
    entries: list[tuple[str, str]],
) -> str:
    """Append up to two similar-parameter tool results after the original output."""
    if not entries:
        return original
    lines = [original.rstrip()]
    for param_summary, tool_result in entries:
        lines.append(f"Similar parameter result ({param_summary}): {tool_result}")
    return "\n".join(lines)


_MISSING_ONE_RE = re.compile(
    r"missing 1 required positional argument: '([^']+)'",
    re.IGNORECASE,
)
_MISSING_MANY_RE = re.compile(
    r"missing \d+ required positional arguments: (.+)$",
    re.IGNORECASE,
)
_UNEXPECTED_KW_RE = re.compile(
    r"got an unexpected keyword argument '([^']+)'",
    re.IGNORECASE,
)


def _parse_simulator_required_params(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        args = node.args
        defaults_offset = len(args.args) - len(args.defaults)
        required = [arg.arg for index, arg in enumerate(args.args) if index < defaults_offset]
        required.extend(
            arg.arg
            for index, arg in enumerate(args.kwonlyargs)
            if args.kw_defaults[index] is None
        )
        return required
    return []


def _param_fill_hint(param: str, schema: dict[str, Any] | None) -> str:
    props = (schema or {}).get("properties") if isinstance(schema, dict) else None
    prop = props.get(param) if isinstance(props, dict) else None
    if not isinstance(prop, dict):
        prop = {}

    enum_values = prop.get("enum")
    if isinstance(enum_values, list) and enum_values:
        rendered = ", ".join(json.dumps(value, ensure_ascii=False) for value in enum_values)
        return f"allowed values: [{rendered}]"

    prop_type = prop.get("type")
    if param in {"date_range", "time_period", "date"} or prop_type == "object":
        if param == "time_period":
            return 'expected object like {"start_year": 1900, "end_year": 2000}'
        return 'expected object like {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}'
    if prop_type == "array":
        return "expected a non-empty JSON array"
    if prop_type == "string":
        description = str(prop.get("description") or "").strip()
        if description:
            return f"expected string ({description[:120]})"
        return "expected a non-empty string"
    if prop_type:
        return f"expected type {prop_type}"
    if param == "date_range":
        return 'expected object like {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}'
    return "required by the tool simulator"


def format_cctu_call_error(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    exc: BaseException,
    schema: dict[str, Any] | None = None,
) -> str:
    """Turn a simulator exception into an observation that still keeps the original error.

    The first line preserves the historical ``an error occured when call ...`` prefix so
    existing failure detectors and suggest-mode fallback keep working. Extra lines only
    disclose how to fill missing/invalid parameters.
    """
    message = str(exc).strip() or type(exc).__name__
    lines = [f"an error occured when call {tool_name}: {message}"]

    missing: list[str] = []
    one = _MISSING_ONE_RE.search(message)
    many = _MISSING_MANY_RE.search(message)
    if one:
        missing = [one.group(1)]
    elif many:
        missing = re.findall(r"'([^']+)'", many.group(1))

    unexpected = _UNEXPECTED_KW_RE.search(message)
    provided = sorted(str(key) for key in arguments.keys())
    required = _parse_simulator_required_params(code)

    if missing:
        lines.append("Missing required parameter(s): " + ", ".join(missing) + ".")
        for param in missing:
            lines.append(f"- {param}: {_param_fill_hint(param, schema)}")
    elif unexpected:
        lines.append(
            f"Unexpected parameter: {unexpected.group(1)}. "
            "Only pass parameters declared by this tool schema."
        )

    if required:
        lines.append("Simulator required parameters: " + ", ".join(required) + ".")
    if provided:
        lines.append("Provided parameters: " + ", ".join(provided) + ".")
    else:
        lines.append("Provided parameters: (none).")
    return "\n".join(lines)


def similar_parameter_results(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    call_function: Callable[..., str],
    min_score: float = DEFAULT_MIN_SCORE,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
) -> list[tuple[str, str]]:
    query_args = normalize_cctu_arguments(tool_name, arguments)
    entries: list[tuple[str, str]] = []
    seen_merged: set[str] = set()
    for golden in rank_golden_candidates(
        tool_name=tool_name,
        arguments=arguments,
        code=code,
        min_score=min_score,
        max_suggestions=max_suggestions,
    ):
        merged = merge_golden_arguments(tool_name, query_args, golden)
        merged_key = json.dumps(merged, sort_keys=True, ensure_ascii=False, default=str)
        if merged_key in seen_merged:
            continue
        seen_merged.add(merged_key)
        try:
            tool_result = call_function(tool_name, merged, code)
        except Exception as exc:  # noqa: BLE001 - mirror tool executor error-as-text behavior
            tool_result = format_cctu_call_error(
                tool_name=tool_name,
                arguments=merged,
                code=code,
                exc=exc,
            )
        if is_failure_result(str(tool_result)) or is_stub_result(str(tool_result)):
            continue
        entries.append((format_suggestion(golden), tool_result))
    return entries


def maybe_append_similar_parameter_results(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    code: str,
    result: str,
    call_function: Callable[..., str],
    min_score: float | None = None,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
) -> str:
    """Suggest mode: keep the original CCTU simulator output unless we can append hints.

    Flow: tool call -> direct hit check -> optional similar-parameter retries -> fallback
    to the original ``result``.  Similar suggestions are appended only when at least one
    golden candidate re-executes successfully.
    """
    if is_direct_hit(tool_name=tool_name, arguments=arguments, code=code, result=result):
        return result
    threshold = DEFAULT_MIN_SCORE if min_score is None else min_score
    entries = similar_parameter_results(
        tool_name=tool_name,
        arguments=arguments,
        code=code,
        call_function=call_function,
        min_score=threshold,
        max_suggestions=max_suggestions,
    )
    if not entries:
        return result
    return format_similar_parameter_results(result, entries)


def cctu_call_function_with_match_mode(
    name: str,
    arguments: dict[str, Any],
    code: str,
    *,
    match_mode: str | None = None,
    call_function: Any,
    schema: dict[str, Any] | None = None,
) -> str:
    """Execute a CCTU simulator, optionally appending similar-parameter hints.

    Flow is always:
    1. call tool (exceptions become enriched original-error text)
    2. if direct hit → return original result
    3. else try similar-parameter suggestions
    4. if suggestions exist → ``original error/result + Similar parameter result (...)``
    5. else → original error/result unchanged
    """
    mode = (match_mode or cctu_tool_match_mode()).strip().lower()
    try:
        result = call_function(name, arguments, code)
    except Exception as exc:  # noqa: BLE001 - preserve CCTU error-as-observation behavior
        result = format_cctu_call_error(
            tool_name=name,
            arguments=arguments,
            code=code,
            exc=exc,
            schema=schema,
        )
    if mode != "suggest":
        return result
    return maybe_append_similar_parameter_results(
        tool_name=name,
        arguments=arguments,
        code=code,
        result=result,
        call_function=call_function,
        min_score=cctu_tool_match_min_score(),
    )
