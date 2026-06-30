#!/usr/bin/env python3
"""Generate evaluator specs for MAC-CCTU anchor and noisy constraints.

The generated artifacts answer a narrow question for each contract-graph node:
did the agent behavior look like it followed this constraint?  The graph oracle
already says whether that node should be active at the evaluation turn; the
grader can combine the oracle label and the observed-followed label into
TP/FP/TN/FN metrics.

The LLM-facing prompt is intentionally compact.  It receives only the constraint
text, weak type hints, and available tool names.  Stable IDs, graph structure,
and output file attributes are added by this script.
"""

from __future__ import annotations

import argparse
import ast
import collections
import csv
import decimal
import hashlib
import importlib
import io
import json
import math
import os
import re
import string
import sys
import threading
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv is optional for dry-run use.
    load_dotenv = None  # type: ignore[assignment]

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_ENV_FILE = Path("bench/.env")
DEFAULT_GRAPHS = Path("bench/MAC/cctu/data/mac-cctu-contract_graphs.json")
DEFAULT_TASKS = Path("bench/MAC/cctu/data/mac-cctu-tasks.json")
DEFAULT_OUTPUT = Path("bench/cctu/mid_data/eval_step5_noise_eval_specs.json")
DEFAULT_CACHE = Path("bench/cctu/mid_data/noise_eval_gen_cache.json")
DEFAULT_ARTIFACT_DIR = Path("bench/MAC/cctu/data/noise_check_code")
CACHE_VERSION = "MACCCTUNoiseEvalGenCacheV1"

SYSTEM_PROMPT = """You convert one agent constraint into a minimal evaluator.
Return strict JSON only. Do not use Markdown.

Goal: decide whether an already-run agent trajectory appears to follow the one
constraint below. Do not decide whether the constraint should apply; the caller
will provide that label from a contract graph.

Important isolation rules:
- Evaluate only the current constraint.
- Do not add checks for answer correctness.
- Do not mix in other constraints such as length, JSON, Markdown, or tool count
  unless the current constraint itself says that.
- If evidence is inherently semantic, return Python code; otherwise prefer a
  structured spec.
- Missing evidence must become unknown in Python code, not a confident pass.
- Keep Python concise, preferably under 80 lines.
- Do not use dunder attributes such as __class__ or __dict__.

Compact structured output schema:
{
  "mode": "structured",
  "family": "response_format|response_length|tool_call_count|specific_tool_call_count|tool_sequence|tool_parallel|tool_usage",
  "spec": {}
}

Supported structured specs:
- response_format: {"checks":[{"name":"markdown_any|bold_any|no_markdown|plain_text|json_object|json_contains_object|contains_terms|excludes_terms|starts_with|ends_with|date_format","terms":["..."],"value":"...","format":"iso|slash|month_year|any"}]}
- response_length: {"unit":"words|characters","min":0|null,"max":10|null}
- tool_call_count: {"min":0|null,"max":5|null}
- specific_tool_call_count: {"per_tool":{"tool_name":{"min":0|null,"max":2|null}}}
- tool_sequence: {"orders":[["tool_a","tool_b"]]}
- tool_parallel: {"groups":[["tool_a","tool_b"]]}
- tool_usage: {"required_tools":["tool_a"],"forbidden_tools":["tool_b"]}

Compact Python output schema, only when structured specs are insufficient:
{
  "mode": "python",
  "code_lines": ["def evaluate(trace):", "    ..."],
  "notes": []
}
Use code_lines for Python so the JSON stays valid. If you use "code" instead,
escape every newline as \\n.

Do not output task ids, node ids, artifact paths, status, evaluator_type,
generation metadata, cache keys, or source graph fields. The local generator
will add those fields after verification.

Python evaluate(trace) input:
- trace["final_response"]: final assistant response string.
- trace["trajectory"]: assistant steps with content and tool_calls.
- trace["tool_calls"]: flattened tool calls with name, arguments, result, index,
  and iteration.

Python evaluate(trace) must return:
{"observed_followed": true|false|null, "confidence": "high|medium|low|unknown", "reason": "...", "evidence_refs": []}

Allowed imports in Python: collections, csv, datetime, decimal, io, json, math,
re, string, typing, unicodedata only.
""".strip()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    target = resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "item"


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_env(env_file: Path | None) -> None:
    if load_dotenv is None:
        return
    if env_file:
        path = resolve_path(env_file)
        if path.exists():
            load_dotenv(path, override=False)
        return
    for candidate in (DEFAULT_ENV_FILE, Path(".env")):
        path = resolve_path(candidate)
        if path.exists():
            load_dotenv(path, override=False)
            return
    load_dotenv(override=False)


def resolve_llm_config(args: argparse.Namespace) -> None:
    if not args.model:
        args.model = os.getenv("LLM_MODEL") or os.getenv("MAC_LLM_MODEL")
    if not args.base_url:
        args.base_url = (
            os.getenv("LLM_BASE_URL")
            or os.getenv("MAC_LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
        )
    if not args.api_key:
        args.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")


def empty_cache() -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
        "items": {},
    }


def load_cache(path: Path) -> dict[str, Any]:
    resolved = resolve_path(path)
    if not resolved.exists():
        return empty_cache()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        raise ValueError(f"Unsupported cache format: {path}")
    if not isinstance(payload.get("items"), dict):
        payload["items"] = {}
    return payload


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json(path, cache)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graphs", type=Path, default=DEFAULT_GRAPHS)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--task-uid", action="append", default=[])
    parser.add_argument(
        "--llm-for",
        choices=["uncovered", "all", "none"],
        default="uncovered",
        help="When to ask the LLM. 'uncovered' uses rules first and asks only for hard cases.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Never call the LLM; emit rule-based or unsupported specs.")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--repair-attempts", type=int, default=3)
    parser.add_argument("--max-llm-calls", type=int, default=None)
    parser.add_argument("--max-workers", type=int, default=1, help="Parallel workers for generation; capped at 8.")
    parser.add_argument("--retry-failed-cache", action="store_true", help="Ignore cached failed/unsupported LLM packages.")
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


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
        raise RuntimeError("openai package is required for live noisy evaluator generation") from exc
    if not model:
        raise ValueError("Missing model. Pass --model or set LLM_MODEL.")
    if not api_key:
        raise ValueError("Missing API key. Pass --api-key or set LLM_API_KEY.")

    client = openai_module.OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout, max_retries=0)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.1,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - provider transport errors should be retried.
            last_error = exc
            if attempt == retries:
                break
            time.sleep(sleep * (2 ** (attempt - 1)))
    raise RuntimeError(f"LLM request failed after {retries} attempts: {last_error}") from last_error


def parse_llm_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        match = re.search(r"```(?:json|python)?\s*(.*?)\s*```", text, flags=re.DOTALL)
        if match:
            text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("LLM response root must be an object")
    return payload


def task_index(tasks_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tasks = tasks_payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("tasks payload must contain tasks list")
    out: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        uid = str(task.get("mac_task_uid") or task.get("task_uid") or "")
        if uid:
            out[uid] = task
    return out


def constraint_meta_index(tasks_by_uid: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for task in tasks_by_uid.values():
        for constraint in task.get("constraints") or []:
            if not isinstance(constraint, dict):
                continue
            uid = str(constraint.get("mac_constraint_uid") or "")
            if uid:
                out[uid] = constraint
    return out


def constraint_type_index(tasks_by_uid: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for task in tasks_by_uid.values():
        for constraint in task.get("constraints") or []:
            if not isinstance(constraint, dict):
                continue
            uid = str(constraint.get("mac_constraint_uid") or "")
            raw_type = constraint.get("type")
            if uid and isinstance(raw_type, list):
                out[uid] = [str(item) for item in raw_type]
    return out


def tool_names_for_task(task: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for tool in task.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        name = tool.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return sorted(set(names))


def selected_graphs(payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    graphs = payload.get("graphs")
    if not isinstance(graphs, list):
        raise ValueError("graphs payload must contain graphs list")
    task_filter = {str(item) for item in args.task_uid}
    chosen = [
        graph for graph in graphs
        if isinstance(graph, dict) and (not task_filter or str(graph.get("task_uid")) in task_filter)
    ]
    offset = max(0, args.offset)
    end = None if args.limit is None else offset + max(0, args.limit)
    return chosen[offset:end]


NUMBER_WORDS = {
    "zero": 0,
    "a": 1,
    "an": 1,
    "one": 1,
    "once": 1,
    "two": 2,
    "twice": 2,
    "three": 3,
    "thrice": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}


def parse_number_token(value: str) -> int | None:
    token = value.strip().lower().replace("_", "-")
    token = re.sub(r"[^a-z0-9-]+", "", token)
    if not token:
        return None
    if token.isdigit():
        return int(token)
    if token in NUMBER_WORDS:
        return NUMBER_WORDS[token]
    parts = [part for part in token.split("-") if part]
    if len(parts) > 1 and all(part in NUMBER_WORDS for part in parts):
        total = 0
        for part in parts:
            if part == "hundred":
                total = max(1, total) * 100
            else:
                total += NUMBER_WORDS[part]
        return total
    return None


def number_after(text: str, patterns: list[str]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = parse_number_token(match.group(1))
            if value is not None:
                return value
    return None


def text_terms_from_quotes(text: str) -> list[str]:
    terms = re.findall(r"`([^`]{2,60})`|\"([^\"]{2,60})\"|'([^']{2,60})'", text)
    out: list[str] = []
    for group in terms:
        value = next((item for item in group if item), "")
        if value:
            out.append(value)
    return out[:8]


def tool_like_names_from_text(text: str) -> list[str]:
    names = re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", text)
    return sorted(set(names))


def response_marker_checks(text: str, lower: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    quoted_terms = text_terms_from_quotes(text)
    if quoted_terms:
        if any(token in lower for token in ("begin", "start", "prepend")):
            checks.append({"name": "starts_with", "value": quoted_terms[0]})
        elif any(token in lower for token in ("end with", "conclude", "append")):
            checks.append({"name": "ends_with", "value": quoted_terms[-1]})
        elif any(token in lower for token in ("include", "contain", "mention", "cite", "wrap")):
            checks.append({"name": "contains_terms", "terms": quoted_terms})

    marker_terms: list[str] = []
    for phrase in (
        "executive summary",
        "follow-up sub-questions",
        "follow-up questions",
        "follow-up",
        "reliability score",
        "confidence score",
        "verification table",
        "source-by-source comparison table",
        "citation list",
        "footnote",
        "timeline",
        "yaml",
        "xml",
        "csv",
        "numbered list",
        "bullet points",
    ):
        if phrase not in lower:
            continue
        if re.search(rf"\b(without|no|avoid|exclude)\b[^.;]{{0,40}}{re.escape(phrase)}", lower):
            continue
        marker_terms.append(phrase)
    for tag in re.findall(r"<([A-Za-z][A-Za-z0-9_-]{1,40})>", text):
        marker_terms.append(f"<{tag}")
    if marker_terms:
        checks.append({"name": "contains_terms", "terms": sorted(set(marker_terms))[:8]})

    if "end with a period" in lower or "ends with a period" in lower:
        checks.append({"name": "ends_with", "value": "."})

    for match in re.finditer(r"\b(?:include|contain|mention)\s+(?:a|an|the)\s+([a-z][a-z0-9 -]{0,30})", lower):
        term = match.group(1).strip()
        if term and term not in {"period", "valid", "single"}:
            checks.append({"name": "contains_terms", "terms": [term]})
            break

    forbidden_punctuation: list[str] = []
    if "no exclamation marks" in lower or "without exclamation marks" in lower:
        forbidden_punctuation.append("!")
    if "no question marks" in lower or "without question marks" in lower:
        forbidden_punctuation.append("?")
    if forbidden_punctuation:
        checks.append({"name": "excludes_terms", "terms": forbidden_punctuation})
    return checks


def package_response_format(checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not checks:
        return None
    return {
        "status": "success",
        "evaluator_type": "structured",
        "family": "response_format",
        "spec": {"checks": checks},
        "generation": {"method": "heuristic"},
    }


def package_response_length(lower: str, type_hint: list[str]) -> dict[str, Any] | None:
    word_max = number_after(
        lower,
        [
            r"(?:at most|no more than|maximum of|max(?:imum)?|under)\s+([A-Za-z0-9-]+)\s+(?:words?|tokens?)",
            r"(?:limit|keep).{0,25}?([A-Za-z0-9-]+)\s+words?",
        ],
    )
    word_min = number_after(lower, [r"(?:at least|minimum of|min(?:imum)?)\s+([A-Za-z0-9-]+)\s+words?"])
    char_max = number_after(
        lower,
        [
            r"(?:at most|no more than|maximum of|max(?:imum)?|under|no more than)\s+([A-Za-z0-9-]+)\s+characters?",
            r"(?:total|limit|keep).{0,25}?([A-Za-z0-9-]+)\s+characters?",
        ],
    )
    char_min = number_after(lower, [r"(?:at least|minimum of|min(?:imum)?)\s+([A-Za-z0-9-]+)\s+characters?"])
    if char_max is not None or char_min is not None:
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "response_length",
            "spec": {"unit": "characters", "min": char_min, "max": char_max},
            "generation": {"method": "heuristic"},
        }
    if word_max is not None or word_min is not None or type_hint == ["Response", "Length"]:
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "response_length",
            "spec": {"unit": "words", "min": word_min, "max": word_max},
            "generation": {"method": "heuristic"},
        }
    return None


def package_total_tool_calls(lower: str) -> dict[str, Any] | None:
    max_calls = number_after(
        lower,
        [
            r"(?:at most|no more than|maximum of|max(?:imum)?|up to)\s+([A-Za-z0-9-]+)\s+(?:\w+\s+){0,3}tool calls?",
            r"(?:limit|keep).{0,30}?([A-Za-z0-9-]+)\s+(?:\w+\s+){0,3}tool calls?",
        ],
    )
    min_calls = number_after(
        lower,
        [
            r"(?:at least|minimum of|min(?:imum)?|execute|make|issue|dispatch)\s+([A-Za-z0-9-]+)\s+(?:\w+\s+){0,3}tool calls?",
            r"(?:at least|minimum of|min(?:imum)?)\s+([A-Za-z0-9-]+)\s+(?:independent|distinct|separate)\s+queries?",
        ],
    )
    if max_calls is None and min_calls is None:
        return None
    return {
        "status": "success",
        "evaluator_type": "structured",
        "family": "tool_call_count",
        "spec": {"min": min_calls, "max": max_calls},
        "generation": {"method": "heuristic"},
    }


def package_specific_tool_calls(lower: str, mentioned_tools: list[str]) -> dict[str, Any] | None:
    per_tool: dict[str, dict[str, int | None]] = {}
    for tool_name in mentioned_tools:
        tool = re.escape(tool_name.lower())
        min_count = number_after(
            lower,
            [
                rf"{tool}.{{0,90}}?(?:at least|minimum of|min(?:imum)?)\s+([A-Za-z0-9-]+)\s+(?:separate\s+)?(?:times?|queries?|tool calls?)",
                rf"(?:at least|minimum of|min(?:imum)?)\s+([A-Za-z0-9-]+)\s+(?:separate\s+)?(?:times?|queries?|tool calls?).{{0,90}}?{tool}",
                rf"(?:invoke|call|use).{{0,50}}?{tool}.{{0,90}}?(?:at least|minimum of|min(?:imum)?)\s+([A-Za-z0-9-]+)",
            ],
        )
        max_count = number_after(
            lower,
            [
                rf"{tool}.{{0,90}}?(?:at most|no more than|maximum of|max(?:imum)?|up to)\s+([A-Za-z0-9-]+)\s+(?:separate\s+)?(?:times?|queries?|tool calls?)",
                rf"(?:at most|no more than|maximum of|max(?:imum)?|up to)\s+([A-Za-z0-9-]+)\s+(?:separate\s+)?(?:times?|queries?|tool calls?).{{0,90}}?{tool}",
            ],
        )
        if min_count is not None or max_count is not None:
            per_tool[tool_name] = {"min": min_count, "max": max_count}
    if not per_tool:
        return None
    return {
        "status": "success",
        "evaluator_type": "structured",
        "family": "specific_tool_call_count",
        "spec": {"per_tool": per_tool},
        "generation": {"method": "heuristic"},
    }


def package_tool_parallel(lower: str, mentioned_tools: list[str]) -> dict[str, Any] | None:
    if len(mentioned_tools) < 2:
        return None
    if not any(
        token in lower
        for token in (
            " in parallel",
            "parallel batch",
            "parallel batches",
            "parallel during",
            "same interaction turn",
            "single coordinated step",
            "simultaneous invocation",
            "simultaneously",
        )
    ):
        return None
    return {
        "status": "success",
        "evaluator_type": "structured",
        "family": "tool_parallel",
        "spec": {"groups": [mentioned_tools]},
        "generation": {"method": "heuristic"},
    }


def package_tool_sequence(lower: str, mentioned_tools: list[str]) -> dict[str, Any] | None:
    if len(mentioned_tools) < 2:
        return None
    orders: list[list[str]] = []
    for first in mentioned_tools:
        first_re = re.escape(first.lower())
        for second in mentioned_tools:
            if first == second:
                continue
            second_re = re.escape(second.lower())
            before_pattern = (
                rf"\b{first_re}\b.{{0,120}}\bbefore\s+(?:any\s+)?"
                rf"(?:(?:call|invocation|lookup|query)\s+(?:to|of|with)\s+|invoking\s+|calling\s+|using\s+|consulting\s+)?"
                rf"(?:the\s+)?\b{second_re}\b(?:\s+(?:call|invocation|lookup|query))?"
            )
            after_pattern = (
                rf"\b{second_re}\b.{{0,120}}\b(?:immediately\s+)?after\s+(?:any\s+)?"
                rf"(?:(?:call|invocation|lookup|query)\s+(?:to|of|with)\s+|invoking\s+|calling\s+|using\s+|consulting\s+)?"
                rf"(?:the\s+)?\b{first_re}\b(?:\s+(?:call|invocation|lookup|query))?"
            )
            if re.search(before_pattern, lower):
                orders.append([first, second])
            elif re.search(after_pattern, lower):
                orders.append([first, second])
    if not orders:
        return None
    deduped: list[list[str]] = []
    seen: set[tuple[str, str]] = set()
    for order in orders:
        key = (order[0], order[1])
        if key not in seen:
            seen.add(key)
            deduped.append(order)
    return {
        "status": "success",
        "evaluator_type": "structured",
        "family": "tool_sequence",
        "spec": {"orders": deduped},
        "generation": {"method": "heuristic"},
    }


def package_tool_usage(lower: str, mentioned_tools: list[str], all_tool_names: list[str]) -> dict[str, Any] | None:
    if not mentioned_tools:
        return None
    if "restrict" in lower and " to " in lower:
        forbidden = [name for name in all_tool_names if name not in set(mentioned_tools)]
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "tool_usage",
            "spec": {"required_tools": mentioned_tools, "forbidden_tools": forbidden},
            "generation": {"method": "heuristic"},
        }
    if any(token in lower for token in ("do not call", "never call", "avoid calling", "forbidden")):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "tool_usage",
            "spec": {"required_tools": [], "forbidden_tools": mentioned_tools},
            "generation": {"method": "heuristic"},
        }
    if any(
        token in lower
        for token in (
            "must call",
            "must invoke",
            "must use",
            "must rely",
            "rely on",
            "invoke ",
            "call ",
            "use ",
            "using ",
            "through ",
            "via ",
            "resolved through",
            "processed through",
            "route ",
            "consult ",
        )
    ):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "tool_usage",
            "spec": {"required_tools": mentioned_tools, "forbidden_tools": []},
            "generation": {"method": "heuristic"},
        }
    return None


def interaction_round_bounds(lower: str) -> dict[str, int | None]:
    max_rounds = number_after(
        lower,
        [
            r"(?:at most|no more than|maximum of|max(?:imum)?|within|finish within|complete within)\s+(?:at most\s+)?([A-Za-z0-9-]+)\s+interaction (?:turns|rounds)",
            r"(?:allowed to make|use)\s+(?:at most|no more than|maximum of|max(?:imum)?)?\s*([A-Za-z0-9-]+)\s+interaction (?:turns|rounds)",
        ],
    )
    min_rounds = number_after(
        lower,
        [
            r"(?:at least|minimum of|min(?:imum)?|after completing at least)\s+([A-Za-z0-9-]+)\s+interaction (?:turns|rounds)",
        ],
    )
    return {"min": min_rounds, "max": max_rounds}


def quoted_identifier_terms(text: str) -> list[str]:
    terms = []
    for term in text_terms_from_quotes(text):
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ -]{0,50}", term):
            terms.append(term)
    return sorted(set(terms))[:12]


def mixed_heuristic_package(text: str, tool_names: list[str], type_hint: list[str]) -> dict[str, Any] | None:
    lower = text.lower()
    mentioned_tools = sorted(
        set(
            [name for name in tool_names if re.search(rf"\b{re.escape(name.lower())}\b", lower)]
            + tool_like_names_from_text(text)
        )
    )
    checks: dict[str, Any] = {}

    word_package = package_response_length(lower, type_hint)
    if word_package and word_package.get("family") == "response_length":
        checks["length"] = word_package.get("spec") or {}

    total_tool_package = package_total_tool_calls(lower)
    if total_tool_package:
        checks["tool_call_count"] = total_tool_package.get("spec") or {}

    specific_tool_package = package_specific_tool_calls(lower, mentioned_tools)
    if specific_tool_package:
        checks["specific_tool_call_count"] = (specific_tool_package.get("spec") or {}).get("per_tool") or {}

    parallel_package = package_tool_parallel(lower, mentioned_tools)
    if parallel_package:
        checks["tool_parallel"] = (parallel_package.get("spec") or {}).get("groups") or []

    rounds = interaction_round_bounds(lower)
    if (rounds.get("min") is not None or rounds.get("max") is not None) and re.search(
        r"\b(interaction|turn|round)s?\b",
        lower,
    ):
        checks["interaction_rounds"] = rounds

    response_checks = response_marker_checks(text, lower)
    if response_checks:
        checks["response_checks"] = response_checks

    if "json object" in lower or "valid json" in lower or "json response" in lower:
        checks["json_object"] = True
        key_terms = quoted_identifier_terms(text)
        key_hints = [term for term in key_terms if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", term)]
        if key_hints:
            checks["json_keys_any"] = key_hints
        if any(token in lower for token in ("only key", "sole key", "only key-value pair")) and key_hints:
            checks["json_only_keys"] = key_hints[:1]

    if any(token in lower for token in ("tabular format", "table", "columns")):
        terms = [term for term in quoted_identifier_terms(text) if " " not in term or len(term) <= 30]
        checks.setdefault("contains_terms", [])
        checks["contains_terms"].extend(terms[:8])

    if "bold" in lower:
        checks["requires_bold"] = True

    if len(checks) < 2:
        return None

    spec_literal = repr(checks)
    code = f'''
import json
import re

SPEC = {spec_literal}


def _word_count(text):
    return len(re.findall(r"\\S+", text or ""))


def _contains_json_object(text):
    text = (text or "").strip()
    candidates = [text]
    candidates.extend(re.findall(r"\\{{.*?\\}}", text, flags=re.DOTALL))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def evaluate(trace):
    trace = trace or {{}}
    final = str(trace.get("final_response") or "")
    trajectory = trace.get("trajectory") or []
    tool_calls = trace.get("tool_calls") or []
    failures = []
    evidence = []

    length = SPEC.get("length") or {{}}
    if length:
        unit = length.get("unit") or "words"
        count = len(final) if unit == "characters" else _word_count(final)
        min_value = length.get("min")
        max_value = length.get("max")
        if isinstance(min_value, int) and count < min_value:
            failures.append(f"{{unit}} length {{count}} below minimum {{min_value}}")
        if isinstance(max_value, int) and count > max_value:
            failures.append(f"{{unit}} length {{count}} above maximum {{max_value}}")
        evidence.append({{"field": "final_response", "unit": unit, "count": count}})

    if SPEC.get("json_object"):
        parsed = _contains_json_object(final)
        if parsed is None:
            failures.append("expected a valid JSON object")
        else:
            keys = set(str(key) for key in parsed.keys())
            required_any = set(str(key) for key in SPEC.get("json_keys_any") or [])
            if required_any and not required_any.intersection(keys):
                failures.append(f"JSON object missing expected key candidates {{sorted(required_any)}}")
            only_keys = set(str(key) for key in SPEC.get("json_only_keys") or [])
            if only_keys and keys != only_keys:
                failures.append(f"JSON object keys {{sorted(keys)}} do not match required keys {{sorted(only_keys)}}")
            evidence.append({{"field": "final_response", "json_keys": sorted(keys)}})

    for term in SPEC.get("contains_terms") or []:
        if str(term).lower() not in final.lower():
            failures.append(f"missing term {{term!r}}")

    if SPEC.get("requires_bold") and not re.search(r"\\*\\*[^*]+\\*\\*|__[^_]+__", final):
        failures.append("expected bold markdown text")

    for check in SPEC.get("response_checks") or []:
        name = check.get("name")
        if name == "ends_with":
            value = str(check.get("value") or "")
            if value and not final.rstrip().endswith(value):
                failures.append(f"response does not end with {{value!r}}")
        elif name == "starts_with":
            value = str(check.get("value") or "")
            if value and not final.startswith(value):
                failures.append(f"response does not start with {{value!r}}")
        elif name == "contains_terms":
            for term in check.get("terms") or []:
                if str(term).lower() not in final.lower():
                    failures.append(f"missing term {{term!r}}")
        elif name == "excludes_terms":
            for term in check.get("terms") or []:
                if str(term) in final:
                    failures.append(f"forbidden term present {{term!r}}")

    rounds = SPEC.get("interaction_rounds") or {{}}
    if rounds:
        count = len(trajectory)
        min_value = rounds.get("min")
        max_value = rounds.get("max")
        if isinstance(min_value, int) and count < min_value:
            failures.append(f"interaction rounds {{count}} below minimum {{min_value}}")
        if isinstance(max_value, int) and count > max_value:
            failures.append(f"interaction rounds {{count}} above maximum {{max_value}}")

    tool_count = SPEC.get("tool_call_count") or {{}}
    if tool_count:
        count = len(tool_calls)
        min_value = tool_count.get("min")
        max_value = tool_count.get("max")
        if isinstance(min_value, int) and count < min_value:
            failures.append(f"tool calls {{count}} below minimum {{min_value}}")
        if isinstance(max_value, int) and count > max_value:
            failures.append(f"tool calls {{count}} above maximum {{max_value}}")

    per_tool = SPEC.get("specific_tool_call_count") or {{}}
    if per_tool:
        counts = {{}}
        for call in tool_calls:
            name = str(call.get("name") or "")
            counts[name] = counts.get(name, 0) + 1
        for tool, bounds in per_tool.items():
            count = counts.get(str(tool), 0)
            min_value = bounds.get("min") if isinstance(bounds, dict) else None
            max_value = bounds.get("max") if isinstance(bounds, dict) else None
            if isinstance(min_value, int) and count < min_value:
                failures.append(f"{{tool}} calls {{count}} below minimum {{min_value}}")
            if isinstance(max_value, int) and count > max_value:
                failures.append(f"{{tool}} calls {{count}} above maximum {{max_value}}")

    groups = SPEC.get("tool_parallel") or []
    if groups:
        step_sets = []
        for step in trajectory:
            step_sets.append({{str(call.get("name") or "") for call in step.get("tool_calls") or [] if isinstance(call, dict)}})
        for group in groups:
            expected = {{str(item) for item in group if item}}
            if expected and not any(expected <= names for names in step_sets):
                failures.append(f"tool group not called in same step: {{sorted(expected)}}")

    if not final and any(key in SPEC for key in ("length", "json_object", "response_checks", "contains_terms", "requires_bold")):
        return {{"observed_followed": None, "confidence": "unknown", "reason": "missing final response", "evidence_refs": evidence}}
    if failures:
        return {{"observed_followed": False, "confidence": "medium", "reason": "; ".join(failures[:8]), "evidence_refs": evidence}}
    return {{"observed_followed": True, "confidence": "medium", "reason": "mixed heuristic checks passed", "evidence_refs": evidence}}
'''.strip()
    return {
        "status": "success",
        "evaluator_type": "python",
        "family": "response_content",
        "check_code": code,
        "notes": ["mixed local heuristic fallback"],
        "generation": {"method": "heuristic"},
    }


def heuristic_package(text: str, tool_names: list[str], type_hint: list[str]) -> dict[str, Any] | None:
    lower = text.lower()
    checks: list[dict[str, Any]] = []

    markdown_negative = "no markdown" in lower or "without markdown" in lower
    if "plain text" in lower:
        checks.append({"name": "plain_text"})
    elif markdown_negative:
        checks.append({"name": "no_markdown"})
    elif "markdown" in lower:
        checks.append({"name": "markdown_any"})
    if "bold" in lower and not markdown_negative:
        checks.append({"name": "bold_any"})
    if "json object" in lower or "valid json" in lower:
        checks.append({"name": "json_object"})
    if "iso 8601" in lower or "yyyy-mm-dd" in lower:
        checks.append({"name": "date_format", "format": "iso"})
    elif "date" in lower and ("mm/dd" in lower or "dd/mm" in lower):
        checks.append({"name": "date_format", "format": "slash"})
    checks.extend(response_marker_checks(text, lower))

    mentioned_tools = sorted(
        set(
            [name for name in tool_names if re.search(rf"\b{re.escape(name.lower())}\b", lower)]
            + tool_like_names_from_text(text)
        )
    )
    specific_tool_package = package_specific_tool_calls(lower, mentioned_tools)
    tool_sequence_package = package_tool_sequence(lower, mentioned_tools)
    tool_parallel_package = package_tool_parallel(lower, mentioned_tools)
    candidate_packages = [
        package_response_format(checks),
        package_response_length(lower, type_hint),
        specific_tool_package,
        tool_sequence_package,
        tool_parallel_package,
        package_total_tool_calls(lower),
        None
        if (specific_tool_package or tool_sequence_package or tool_parallel_package)
        else package_tool_usage(lower, mentioned_tools, tool_names),
    ]
    candidate_packages = [package for package in candidate_packages if package is not None]
    if len(candidate_packages) == 1:
        return candidate_packages[0]
    return None


def none_if_inf(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() == "inf":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def cctu_json_package(constraint: dict[str, Any]) -> dict[str, Any] | None:
    check_path = constraint.get("check_path")
    if not isinstance(check_path, str) or not check_path:
        return None
    path = REPO_ROOT / "bench" / "CCTU" / check_path
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_type = constraint.get("type")
    type_key = tuple(str(item) for item in raw_type) if isinstance(raw_type, list) else ()
    generation = {"method": "cctu_reference", "source_artifact": str(path.relative_to(REPO_ROOT))}
    if type_key == ("Resource", "Interaction Rounds"):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "interaction_rounds",
            "spec": {"min": none_if_inf(data.get("min_round")), "max": none_if_inf(data.get("max_round"))},
            "generation": generation,
        }
    if type_key == ("Resource", "Tool Call Count"):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "tool_call_count",
            "spec": {"min": none_if_inf(data.get("min_callTimes")), "max": none_if_inf(data.get("max_callTimes"))},
            "generation": generation,
        }
    if type_key == ("Resource", "Specific Tool Call Count"):
        per_tool = {
            str(tool): {"min": None, "max": none_if_inf(limit)}
            for tool, limit in (data.get("max_calls_per_tool") or {}).items()
        }
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "specific_tool_call_count",
            "spec": {"per_tool": per_tool},
            "generation": generation,
        }
    if type_key == ("Behavior", "Sequential Dependencies"):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "tool_sequence",
            "spec": {"orders": data.get("order_constraints") or []},
            "generation": generation,
        }
    if type_key == ("Behavior", "Parallel Dependencies"):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "tool_parallel",
            "spec": {"groups": data.get("parallel_groups") or []},
            "generation": generation,
        }
    if type_key == ("Behavior", "Parallel Calls Count"):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "parallel_call_count",
            "spec": {
                "min": none_if_inf(data.get("min_parallelCallTypes")),
                "max": none_if_inf(data.get("max_parallelCallTypes")),
                "unit": data.get("unit") or "type",
            },
            "generation": generation,
        }
    if type_key == ("Response", "Length"):
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": "response_length",
            "spec": {
                "unit": data.get("unit") or "words",
                "min": none_if_inf(data.get("min_responseLength")),
                "max": none_if_inf(data.get("max_responseLength")),
            },
            "generation": generation,
        }
    return None


def cctu_python_function_name(constraint: dict[str, Any]) -> str | None:
    raw_type = constraint.get("type")
    type_key = tuple(str(item) for item in raw_type) if isinstance(raw_type, list) else ()
    if type_key == ("Response", "Format"):
        return "validate_format"
    if type_key == ("Response", "Content_1"):
        return "validate_identifiers"
    if type_key == ("Response", "Content_2"):
        return "validate_punctuation"
    return None


def cctu_python_family(constraint: dict[str, Any]) -> str:
    raw_type = constraint.get("type")
    type_key = tuple(str(item) for item in raw_type) if isinstance(raw_type, list) else ()
    if type_key == ("Response", "Format"):
        return "response_format"
    return "response_content"


def cctu_python_package(constraint: dict[str, Any]) -> dict[str, Any] | None:
    function_name = cctu_python_function_name(constraint)
    check_path = constraint.get("check_path")
    if not function_name or not isinstance(check_path, str) or not check_path:
        return None
    path = REPO_ROOT / "bench" / "CCTU" / check_path
    if not path.exists():
        return None
    source = path.read_text(encoding="utf-8").rstrip()
    wrapper = f'''


def evaluate(trace):
    response = str((trace or {{}}).get("final_response") or "")
    if not response:
        return {{
            "observed_followed": None,
            "confidence": "unknown",
            "reason": "missing final response",
            "evidence_refs": [],
        }}
    ok, message = {function_name}(response)
    return {{
        "observed_followed": bool(ok),
        "confidence": "high",
        "reason": str(message),
        "evidence_refs": [{{"field": "final_response"}}],
    }}
'''.rstrip()
    return {
        "status": "success",
        "evaluator_type": "python",
        "family": cctu_python_family(constraint),
        "check_code": source + wrapper,
        "generation": {"method": "cctu_reference", "source_artifact": str(path.relative_to(REPO_ROOT))},
    }


def cctu_anchor_package(node: dict[str, Any], constraint_meta_by_uid: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if node.get("is_anchor") is not True:
        return None
    source_uid = str(node.get("source_constraint_uid") or "")
    constraint = constraint_meta_by_uid.get(source_uid)
    if not constraint:
        return None
    if constraint.get("check_artifact_type") == "json":
        return cctu_json_package(constraint)
    if constraint.get("check_artifact_type") == "py":
        return cctu_python_package(constraint)
    return None


def build_llm_prompt(*, text: str, type_hint: list[str], tool_names: list[str], previous_errors: list[str] | None = None) -> str:
    payload: dict[str, Any] = {
        "constraint": text,
        "weak_type_hint": " / ".join(type_hint) if type_hint else None,
        "available_tool_names": tool_names[:30],
        "instruction": (
            "Return the smallest evaluator that detects whether the trajectory follows this constraint. "
            "Prefer structured specs for count, order, parallel, tool usage, length, and simple response format checks. "
            "Return only compact key information; local code will add ids and package attributes."
        ),
    }
    if previous_errors:
        payload["previous_verifier_errors"] = previous_errors
        payload["repair_instruction"] = "Return corrected compact JSON only."
    return json.dumps(payload, indent=2, ensure_ascii=False)


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
BLOCKED_CALLS = {
    "__import__",
    "compile",
    "delattr",
    "eval",
    "exec",
    "getattr",
    "globals",
    "hasattr",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}


def verify_python_code(code: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    evaluate = next((node for node in functions if node.name == "evaluate"), None)
    if evaluate is None:
        errors.append("missing evaluate(trace) function")
    else:
        args = [arg.arg for arg in evaluate.args.args]
        if args != ["trace"] or evaluate.args.vararg or evaluate.args.kwarg:
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

    if errors:
        return sorted(set(errors))
    def safe_import(name: str, globals_: Any = None, locals_: Any = None, fromlist: Any = (), level: int = 0) -> Any:
        root = str(name).split(".", 1)[0]
        if root not in ALLOWED_IMPORTS:
            raise ImportError(f"import not allowed: {name}")
        return __import__(name, globals_, locals_, fromlist, level)

    safe_builtins = {
        "Exception": Exception,
        "KeyError": KeyError,
        "TypeError": TypeError,
        "ValueError": ValueError,
        "__import__": safe_import,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "float": float,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "range": range,
        "reversed": reversed,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
    }
    exec_env: dict[str, Any] = {
        "__builtins__": safe_builtins,
        "collections": collections,
        "csv": csv,
        "datetime": datetime,
        "decimal": decimal,
        "io": io,
        "json": json,
        "math": math,
        "re": re,
        "string": string,
        "unicodedata": unicodedata,
    }
    try:
        exec(compile(tree, "<noise-evaluator>", "exec"), exec_env)  # noqa: S102 - generated code is pre-verified and sandboxed.
        result = exec_env["evaluate"]({"final_response": "", "trajectory": [], "tool_calls": []})
    except Exception as exc:  # noqa: BLE001 - verifier should return structured errors.
        return [f"evaluate smoke test failed: {type(exc).__name__}: {exc}"]
    if not isinstance(result, dict):
        return ["evaluate must return a dict"]
    if result.get("observed_followed") not in {True, False, None}:
        return ["observed_followed must be true, false, or null"]
    return []


def verify_structured_package(payload: dict[str, Any]) -> list[str]:
    family = payload.get("family")
    spec = payload.get("spec")
    if not isinstance(family, str):
        return ["structured package missing family"]
    if not isinstance(spec, dict):
        return ["structured package missing spec object"]
    known = {
        "interaction_rounds",
        "parallel_call_count",
        "response_format",
        "response_length",
        "tool_call_count",
        "specific_tool_call_count",
        "tool_sequence",
        "tool_parallel",
        "tool_usage",
    }
    if family not in known:
        return [f"unknown structured family: {family}"]
    if family == "response_format" and not isinstance(spec.get("checks"), list):
        return ["response_format requires checks list"]
    if family == "response_length" and spec.get("unit") not in {"words", "characters"}:
        return ["response_length unit must be words or characters"]
    if family == "parallel_call_count" and spec.get("unit") not in {"type", "num", "number", None}:
        return ["parallel_call_count unit must be type or num"]
    if family == "specific_tool_call_count" and not isinstance(spec.get("per_tool"), dict):
        return ["specific_tool_call_count requires per_tool object"]
    if family == "tool_sequence" and not isinstance(spec.get("orders"), list):
        return ["tool_sequence requires orders list"]
    if family == "tool_parallel" and not isinstance(spec.get("groups"), list):
        return ["tool_parallel requires groups list"]
    if family == "tool_usage" and not (
        isinstance(spec.get("required_tools", []), list) and isinstance(spec.get("forbidden_tools", []), list)
    ):
        return ["tool_usage requires required_tools and forbidden_tools arrays"]
    return []


def package_from_compact_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("evaluator_type") in {"structured", "python"}:
        return payload
    mode = str(payload.get("mode") or payload.get("kind") or payload.get("type") or "").strip().lower()
    if mode == "structured":
        return {
            "status": "success",
            "evaluator_type": "structured",
            "family": payload.get("family"),
            "spec": payload.get("spec") if isinstance(payload.get("spec"), dict) else {},
            "notes": payload.get("notes") if isinstance(payload.get("notes"), list) else [],
        }
    if mode == "python":
        code = payload.get("code") or payload.get("check_code")
        code_lines = payload.get("code_lines")
        if not isinstance(code, str) and isinstance(code_lines, list):
            code = "\n".join(str(line) for line in code_lines)
        return {
            "status": "success",
            "evaluator_type": "python",
            "check_code": code,
            "notes": payload.get("notes") if isinstance(payload.get("notes"), list) else [],
        }
    if mode in {"unsupported", "none", "unknown"}:
        return {
            "status": "unsupported",
            "evaluator_type": "unsupported",
            "notes": [str(payload.get("reason") or "LLM returned unsupported")],
            "generation": {"method": "llm_unsupported"},
        }
    return payload


def normalize_package(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(package_from_compact_llm_payload(payload))
    status = str(normalized.get("status") or "success").strip().lower()
    normalized["status"] = "success" if status in {"success", "ok", "ready", "valid"} else "unsupported"
    evaluator_type = str(normalized.get("evaluator_type") or "").strip().lower()
    if evaluator_type not in {"structured", "python"}:
        normalized["status"] = "unsupported"
        normalized["evaluator_type"] = "unsupported"
        normalized.setdefault("notes", ["unknown evaluator_type"])
        return normalized
    normalized["evaluator_type"] = evaluator_type
    if evaluator_type == "python" and isinstance(normalized.get("check_code"), str):
        normalized["check_code"] = clean_code(normalized["check_code"])
    return normalized


def clean_code(code: str) -> str:
    stripped = code.strip()
    if not stripped.startswith("```"):
        return stripped
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    return match.group(1).strip() if match else stripped


def verify_package(payload: dict[str, Any]) -> list[str]:
    if payload.get("status") != "success":
        return []
    if payload.get("evaluator_type") == "structured":
        return verify_structured_package(payload)
    if payload.get("evaluator_type") == "python":
        code = payload.get("check_code")
        if not isinstance(code, str) or not code.strip():
            return ["python package missing check_code"]
        return verify_python_code(code)
    return ["unsupported evaluator_type"]


def package_from_llm(
    *,
    text: str,
    type_hint: list[str],
    tool_names: list[str],
    args: argparse.Namespace,
    cache: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    errors: list[str] = []
    prompt_key_payload = {
        "constraint_text_sha256": sha256_text(text),
        "type_hint": type_hint,
        "tool_names": tool_names,
        "model": args.model,
        "prompt_version": 4,
    }
    cache_key = sha256_text(stable_json(prompt_key_payload))
    cache_lock = getattr(args, "_cache_lock", None)
    if cache_lock is None:
        cached = cache["items"].get(cache_key)
    else:
        with cache_lock:
            cached = cache["items"].get(cache_key)
    if isinstance(cached, dict):
        normalized_cached = normalize_package(cached)
        method = (
            (normalized_cached.get("generation") or {}).get("method")
            if isinstance(normalized_cached.get("generation"), dict)
            else None
        )
        cached_errors = verify_package(normalized_cached)
        if args.retry_failed_cache and (
            normalized_cached.get("status") != "success"
            or cached_errors
            or method in {"llm_failed", "llm_unsupported"}
        ):
            cached = None
    if isinstance(cached, dict):
        return cached, "hit"

    for attempt in range(1, max(1, args.repair_attempts) + 1):
        prompt = build_llm_prompt(text=text, type_hint=type_hint, tool_names=tool_names, previous_errors=errors or None)
        raw = call_llm(
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            prompt=prompt,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            retries=args.retries,
            sleep=args.sleep,
        )
        try:
            package = normalize_package(parse_llm_json(raw))
            errors = verify_package(package)
            if not errors:
                package.setdefault("generation", {})
                package["generation"] = {"method": "llm", "attempts": attempt}
                if cache_lock is None:
                    cache["items"][cache_key] = package
                else:
                    with cache_lock:
                        cache["items"][cache_key] = package
                return package, "miss"
        except Exception as exc:  # noqa: BLE001 - verifier feedback drives repair.
            errors = [f"invalid response: {type(exc).__name__}: {exc}"]

    package = {
        "status": "unsupported",
        "evaluator_type": "unsupported",
        "notes": ["LLM package failed verification", *errors],
        "generation": {"method": "llm_failed"},
    }
    if cache_lock is None:
        cache["items"][cache_key] = package
    else:
        with cache_lock:
            cache["items"][cache_key] = package
    return package, "miss"


def unsupported_package(reason: str) -> dict[str, Any]:
    return {
        "status": "unsupported",
        "evaluator_type": "unsupported",
        "notes": [reason],
        "generation": {"method": "rulebase_uncovered"},
    }


def build_artifact_payload(
    *,
    package: dict[str, Any],
    node: dict[str, Any],
    task_uid: str,
    node_id: str,
    expected_should_apply: bool,
    type_hint: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "MACCCTUNoiseEvaluatorArtifactV1",
        "task_uid": task_uid,
        "node_id": node_id,
        "constraint_text": node.get("text", ""),
        "expected_should_apply": expected_should_apply,
        "is_anchor": bool(node.get("is_anchor")),
        "source_constraint_uid": node.get("source_constraint_uid"),
        "source_anchor_role": node.get("source_anchor_role"),
        "trigger_condition_holds": node.get("trigger_condition_holds"),
        "type_hint": type_hint,
        "evaluator": {
            key: value
            for key, value in package.items()
            if key not in {"check_code"}
        },
    }


def write_artifacts(
    *,
    artifact_dir: Path,
    task_uid: str,
    node_id: str,
    artifact_payload: dict[str, Any],
    package: dict[str, Any],
) -> tuple[str, str | None]:
    base_dir = resolve_path(artifact_dir) / safe_name(task_uid)
    base_dir.mkdir(parents=True, exist_ok=True)
    json_path = base_dir / f"{safe_name(node_id)}.json"
    json_path.write_text(json.dumps(artifact_payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    code_rel: str | None = None
    if package.get("evaluator_type") == "python" and isinstance(package.get("check_code"), str):
        code_path = base_dir / f"{safe_name(node_id)}.py"
        code_path.write_text(package["check_code"].rstrip() + "\n", encoding="utf-8")
        code_rel = display_path(code_path)
    return display_path(json_path), code_rel


def reserve_llm_call(package: dict[str, Any] | None, args: argparse.Namespace) -> bool:
    if args.dry_run or args.llm_for == "none":
        return False
    if args.llm_for == "all":
        needed = True
    else:
        needed = package is None
    if not needed:
        return False
    lock = getattr(args, "_llm_call_lock", None)
    if lock is None:
        if args.max_llm_calls is not None and getattr(args, "_llm_calls_used", 0) >= args.max_llm_calls:
            return False
        args._llm_calls_used = getattr(args, "_llm_calls_used", 0) + 1
        return True
    with lock:
        if args.max_llm_calls is not None and getattr(args, "_llm_calls_used", 0) >= args.max_llm_calls:
            return False
        args._llm_calls_used = getattr(args, "_llm_calls_used", 0) + 1
        return True


def process_node(
    *,
    node: dict[str, Any],
    graph: dict[str, Any],
    task: dict[str, Any],
    type_by_constraint_uid: dict[str, list[str]],
    constraint_meta_by_uid: dict[str, dict[str, Any]],
    args: argparse.Namespace,
    cache: dict[str, Any],
) -> dict[str, Any]:
    task_uid = str(graph.get("task_uid") or task.get("mac_task_uid") or "")
    node_id = str(node.get("local_id") or "")
    text = str(node.get("text") or "")
    expected_active = set(str(item) for item in (graph.get("oracle") or {}).get("expected_active_node_ids") or [])
    expected_should_apply = node_id in expected_active
    source_uid = str(node.get("source_constraint_uid") or "")
    type_hint = type_by_constraint_uid.get(source_uid, [])
    tool_names = tool_names_for_task(task)

    package = cctu_anchor_package(node, constraint_meta_by_uid)
    if package is None:
        package = heuristic_package(text, tool_names, type_hint)
    cache_status = "not_used"
    if reserve_llm_call(package, args):
        package, cache_status = package_from_llm(
            text=text,
            type_hint=type_hint,
            tool_names=tool_names,
            args=args,
            cache=cache,
        )
    if package is None:
        package = unsupported_package("rulebase did not cover this constraint; run without --dry-run and with --llm-for uncovered")

    package = normalize_package(package)
    verifier_errors = verify_package(package)
    if package.get("status") != "success" or verifier_errors:
        fallback = mixed_heuristic_package(text, tool_names, type_hint)
        if fallback:
            fallback = normalize_package(fallback)
            fallback_errors = verify_package(fallback)
            if not fallback_errors:
                package = fallback
                verifier_errors = []
    if verifier_errors:
        package = unsupported_package("verifier rejected package: " + "; ".join(verifier_errors))

    artifact_payload = build_artifact_payload(
        package=package,
        node=node,
        task_uid=task_uid,
        node_id=node_id,
        expected_should_apply=expected_should_apply,
        type_hint=type_hint,
    )
    artifact_rel, code_rel = write_artifacts(
        artifact_dir=args.artifact_dir,
        task_uid=task_uid,
        node_id=node_id,
        artifact_payload=artifact_payload,
        package=package,
    )
    return {
        "task_uid": task_uid,
        "node_id": node_id,
        "artifact_path": artifact_rel,
        "code_path": code_rel,
        "expected_should_apply": expected_should_apply,
        "is_anchor": bool(node.get("is_anchor")),
        "trigger_condition_holds": node.get("trigger_condition_holds"),
        "source_constraint_uid": source_uid,
        "source_anchor_role": node.get("source_anchor_role"),
        "evaluator_type": package.get("evaluator_type"),
        "family": package.get("family"),
        "status": package.get("status"),
        "generation_method": (package.get("generation") or {}).get("method"),
        "cache": cache_status,
        "constraint_text_sha256": sha256_text(text),
    }


def summarize(units: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "unit_count": len(units),
        "expected_active_count": sum(1 for unit in units if unit.get("expected_should_apply")),
        "anchor_count": sum(1 for unit in units if unit.get("is_anchor")),
        "status_distribution": dict(Counter(str(unit.get("status")) for unit in units)),
        "evaluator_type_distribution": dict(Counter(str(unit.get("evaluator_type")) for unit in units)),
        "family_distribution": dict(Counter(str(unit.get("family")) for unit in units if unit.get("family"))),
        "generation_method_distribution": dict(Counter(str(unit.get("generation_method")) for unit in units)),
    }


def main() -> int:
    args = parse_args()
    args.max_workers = min(8, max(1, args.max_workers))
    args._llm_calls_used = 0
    args._llm_call_lock = threading.Lock()
    args._cache_lock = threading.Lock()
    load_env(args.env_file)
    resolve_llm_config(args)
    graphs_payload = load_json(args.graphs)
    tasks_payload = load_json(args.tasks)
    tasks_by_uid = task_index(tasks_payload)
    type_by_constraint_uid = constraint_type_index(tasks_by_uid)
    constraint_meta_by_uid = constraint_meta_index(tasks_by_uid)
    cache = load_cache(args.cache)

    graphs = selected_graphs(graphs_payload, args)
    jobs: list[tuple[int, dict[str, Any], dict[str, Any], dict[str, Any], str]] = []
    for graph in graphs:
        task_uid = str(graph.get("task_uid") or "")
        task = tasks_by_uid.get(task_uid, {})
        for node in graph.get("generated_constraints") or []:
            if not isinstance(node, dict):
                continue
            jobs.append((len(jobs), graph, task, node, task_uid))

    total_nodes = len(jobs)
    units_by_index: list[dict[str, Any] | None] = [None] * total_nodes

    def run_job(job: tuple[int, dict[str, Any], dict[str, Any], dict[str, Any], str]) -> tuple[int, dict[str, Any]]:
        index, graph, task, node, _task_uid = job
        return index, process_node(
            node=node,
            graph=graph,
            task=task,
            type_by_constraint_uid=type_by_constraint_uid,
            constraint_meta_by_uid=constraint_meta_by_uid,
            args=args,
            cache=cache,
        )

    def maybe_print_progress(done: int, task_uid: str, node_id: Any) -> None:
        if (
            not args.quiet
            and args.progress_every > 0
            and (done == 1 or done == total_nodes or done % args.progress_every == 0)
        ):
            print(f"noise-eval {done}/{total_nodes} task={task_uid} node={node_id}", flush=True)

    if args.max_workers == 1:
        for done, job in enumerate(jobs, start=1):
            index, _graph, _task, node, task_uid = job
            maybe_print_progress(done, task_uid, node.get("local_id"))
            index, unit = run_job(job)
            units_by_index[index] = unit
    else:
        done = 0
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_to_job = {executor.submit(run_job, job): job for job in jobs}
            for future in as_completed(future_to_job):
                job = future_to_job[future]
                index, _graph, _task, node, task_uid = job
                result_index, unit = future.result()
                units_by_index[result_index] = unit
                done += 1
                maybe_print_progress(done, task_uid, node.get("local_id"))

    missing = [index for index, unit in enumerate(units_by_index) if unit is None]
    if missing:
        raise RuntimeError(f"generation failed to produce {len(missing)} units; first missing index={missing[0]}")
    units = [
        unit
        for unit in units_by_index
        if unit is not None
    ]

    save_cache(args.cache, cache)
    payload = {
        "schema_version": "MACCCTUNoiseEvalSpecManifestV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_graphs": str(args.graphs),
        "source_tasks": str(args.tasks),
        "artifact_dir": str(args.artifact_dir),
        "llm": {
            "model": args.model if not args.dry_run and args.llm_for != "none" else None,
            "base_url_configured": bool(args.base_url) if not args.dry_run and args.llm_for != "none" else False,
            "mode": "dry_run" if args.dry_run else args.llm_for,
            "max_llm_calls": args.max_llm_calls,
            "llm_calls_used": getattr(args, "_llm_calls_used", 0),
        },
        "summary": summarize(units),
        "units": units,
    }
    write_json(args.output, payload)
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))
    print(f"Wrote {resolve_path(args.output)}")
    print(f"Wrote evaluator artifacts under {resolve_path(args.artifact_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
