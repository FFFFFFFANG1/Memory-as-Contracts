#!/usr/bin/env python3
"""Remove selected constraints from task prompts with an LLM.

Input tasks are kept structurally unchanged: this script only rewrites
``task["input"][*]["content"]``. The LLM sees a compact payload containing the
message being rewritten plus the task's ``constraints[*].desc`` values, and
returns only exact text spans to remove. Python applies those removals locally.

A processed prompt library is maintained separately, keyed by role, exact prompt
content, and the constraint descriptions to remove. This lets repeated system
prompts reuse the same cleaned prompt without another LLM call.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_VERSION = 1

SYSTEM_PROMPT = """
You clean benchmark prompts.

You will receive one prompt message and a list of constraint descriptions that
were extracted from the original task. Remove only the explicit instructions,
rules, formatting requirements, prohibitions, or preference constraints that
correspond to those descriptions.

Preserve everything else exactly as much as possible:
- Keep the agent role and task description.
- Keep user-provided facts, scenario details, domain context, examples, data,
  and any non-constraint content.
- Keep wording, order, paragraph breaks, and punctuation unless removing a
  listed constraint makes a small cleanup necessary.
- Do not add new instructions.
- Do not summarize or rewrite broadly.

If none of the listed constraints appear in the message, return the original
message content unchanged.

Return valid JSON only, with this schema:
{"remove": ["exact substring from the input message to delete"]}

Rules for "remove":
- Each item must be copied verbatim from the input message.
- Include only text that should be deleted.
- Prefer the smallest contiguous span that removes the listed constraint cleanly.
- Include surrounding newlines only when they should also be removed.
- Return an empty list if none of the listed constraints appear in the message.
""".strip()


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


def load_env(env_file: Path | None) -> None:
    if env_file:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def constraint_descs(task: dict[str, Any]) -> list[dict[str, str]]:
    descs: list[dict[str, str]] = []
    for index, constraint in enumerate(task.get("constraints", [])):
        if not isinstance(constraint, dict):
            continue
        desc = constraint.get("desc")
        if not isinstance(desc, str) or not desc.strip():
            continue
        descs.append(
            {
                "constraint_uid": str(
                    constraint.get(
                        "mac_constraint_uid",
                        f"{task.get('mac_task_uid', 'task')}-c{index + 1:04d}",
                    )
                ),
                "desc": desc.strip(),
            }
        )
    return descs


def cache_key(*, role: str, content: str, constraints: list[dict[str, str]]) -> str:
    payload = {
        "role": role,
        "content": content,
        "constraints": sorted((item["desc"] for item in constraints)),
    }
    return sha256_text(stable_json(payload))


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
        raise ValueError(f"Prompt cache must be a JSON object: {path}")
    if cache.get("version") != CACHE_VERSION:
        raise ValueError(f"Unsupported prompt cache version in {path}: {cache.get('version')}")
    if not isinstance(cache.get("items"), dict):
        cache["items"] = {}
    return cache


def record_cache_item(
    cache: dict[str, Any],
    *,
    key: str,
    role: str,
    content: str,
    constraints: list[dict[str, str]],
    removed_patterns: list[str],
    unmatched_patterns: list[str],
    model: str,
    task_uid: str,
) -> None:
    existing_task_uids = cache["items"].get(key, {}).get("task_uids", [])
    cache["items"][key] = {
        "role": role,
        "content_hash": sha256_text(content),
        "constraints_hash": sha256_text(stable_json(sorted(item["desc"] for item in constraints))),
        "removed_patterns": removed_patterns,
        "unmatched_patterns": unmatched_patterns,
        "model": model,
        "task_uids": sorted({task_uid, *existing_task_uids}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()


def build_prompt(
    *,
    task_uid: str,
    message_index: int,
    role: str,
    content: str,
    constraints: list[dict[str, str]],
) -> str:
    payload = {
        "task_uid": task_uid,
        "message_index": message_index,
        "input": [
            {
                "role": role,
                "content": content,
            }
        ],
        "constraints": [{"desc": item["desc"]} for item in constraints],
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
        raise RuntimeError("openai package is required for live prompt filtering") from exc

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
                temperature=0.0,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - CLI should retry provider errors.
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
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    removals = payload.get("remove", payload.get("removals"))
    if not isinstance(removals, list) or not all(isinstance(item, str) for item in removals):
        raise ValueError("LLM JSON must contain string list field 'remove'")
    return payload


def whitespace_flexible_pattern(text: str) -> str:
    parts = re.split(r"\s+", text.strip())
    return r"\s+".join(re.escape(part) for part in parts if part)


def apply_removals(content: str, removals: list[str]) -> tuple[str, list[str], list[str]]:
    cleaned = content
    applied: list[str] = []
    unmatched: list[str] = []

    for removal in removals:
        if not removal:
            continue
        if removal in cleaned:
            cleaned = cleaned.replace(removal, "", 1)
            applied.append(removal)
            continue

        pattern = whitespace_flexible_pattern(removal)
        if not pattern:
            continue
        updated, count = re.subn(pattern, "", cleaned, count=1)
        if count:
            cleaned = updated
            applied.append(removal)
        else:
            unmatched.append(removal)

    return cleaned, applied, unmatched


def normalize_match_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"^[\s>*#`'\"-]*(?:\d+[.)]\s*)?", "", text)
    text = re.sub(r"[`*_\"'.,:;!?()\[\]{}\\]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def line_span_at(content: str, start: int, end: int) -> str:
    line_start = content.rfind("\n", 0, start) + 1
    line_end = content.find("\n", end)
    if line_end == -1:
        line_end = len(content)
    else:
        line_end += 1
    return content[line_start:line_end]


def balanced_jsonish_span(content: str, start: int) -> str | None:
    depth = 0
    in_string = False
    escaped = False
    end = start
    for index in range(start, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if depth != 0:
        return None
    while end < len(content) and content[end] in " \t\r\n":
        end += 1
    if end < len(content) and content[end] == ",":
        end += 1
    return content[start:end]


def tool_schema_span(content: str, tool_name: str) -> str | None:
    name_patterns = [f'"name":"{tool_name}"', f'"name": "{tool_name}"']
    idx = -1
    for pattern in name_patterns:
        idx = content.find(pattern)
        if idx != -1:
            break
    if idx == -1:
        return None
    start = content.rfind('{"type":"function"', 0, idx)
    if start == -1:
        start = content.rfind('{"type": "function"', 0, idx)
    if start == -1:
        return line_span_at(content, idx, idx + len(tool_name))
    return balanced_jsonish_span(content, start) or line_span_at(content, idx, idx + len(tool_name))


def fenced_block_span_at(content: str, start: int, end: int) -> str:
    line = line_span_at(content, start, end)
    line_start = content.rfind("\n", 0, start) + 1
    block_end = line_start + len(line)
    fence_start = content.find("```", block_end)
    if fence_start == -1 or fence_start > block_end + 500:
        return line
    fence_end = content.find("```", fence_start + 3)
    if fence_end == -1:
        return line
    after_fence = content.find("\n", fence_end + 3)
    block_end = len(content) if after_fence == -1 else after_fence + 1
    return content[line_start:block_end]


def local_removal_for_desc(content: str, desc: str) -> str | None:
    if desc.startswith("Format-"):
        return tool_schema_span(content, desc.removeprefix("Format-"))

    if "ONLY acceptable format for code citations" in desc:
        start = content.find("You MUST use the following format when citing code regions or blocks:")
        if start != -1:
            end = content.find('"tools":', start)
            if end != -1:
                return content[start:end]

    direct_candidates = [desc]
    if desc.endswith("."):
        direct_candidates.append(desc[:-1])
    for candidate in direct_candidates:
        if candidate and candidate in content:
            idx = content.find(candidate)
            return line_span_at(content, idx, idx + len(candidate))

    tag_match = re.search(r"<[^>\s]+>", desc)
    if tag_match:
        tag = tag_match.group(0)
        idx = content.find(tag)
        if idx != -1:
            return line_span_at(content, idx, idx + len(tag))

    normalized_desc = normalize_match_text(desc)
    if not normalized_desc:
        return None

    for line in content.splitlines(keepends=True):
        normalized_line = normalize_match_text(line)
        if not normalized_line:
            continue
        if normalized_desc == normalized_line or normalized_desc in normalized_line:
            idx = content.find(line)
            if idx == -1:
                continue
            if "tanstack" in normalized_desc and "usequery" in normalized_desc:
                return fenced_block_span_at(content, idx, idx + len(line))
            return line

    # A few common extracted descriptions merge neighboring prompt sentences.
    # Match by distinctive tokens, but still delete only a local line/block.
    distinctive_terms = [
        "Create small, focused components",
        "Use TypeScript for type safety",
        "Write extensive console logs for debugging",
        "inline math",
        "block math",
        "NEVER add copyright or license headers",
        "You do not need to `git commit` your changes",
        "pre-commit run --files",
        "NEVER call tools that are not explicitly provided",
        "This is the ONLY acceptable format for code citations",
    ]
    for term in distinctive_terms:
        if normalize_match_text(term) in normalized_desc:
            idx = content.lower().find(term.lower())
            if idx != -1:
                return line_span_at(content, idx, idx + len(term))
    return None


def local_removals(
    content: str,
    constraints: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, str]]]:
    removals: list[str] = []
    unmatched: list[dict[str, str]] = []
    seen: set[str] = set()
    working = content
    for constraint in constraints:
        desc = constraint["desc"]
        removal = local_removal_for_desc(working, desc)
        if removal:
            if removal not in seen:
                removals.append(removal)
                seen.add(removal)
                working = working.replace(removal, "", 1)
        elif desc.startswith("Format-"):
            # Some extracted tool-format constraints refer to legacy tools that
            # are no longer present in this prompt. There is nothing to remove.
            continue
        elif any(term in desc.lower() for term in ("inline math", "block math")) and not any(
            term in working.lower() for term in ("inline math", "block math")
        ):
            continue
        else:
            unmatched.append(constraint)
    return removals, unmatched


def cleaned_from_cache(
    *,
    message: dict[str, Any],
    content: str,
    cached: dict[str, Any],
    task_uid: str,
) -> dict[str, Any] | None:
    cleaned = copy.deepcopy(message)
    if isinstance(cached.get("processed_content"), str):
        cleaned["content"] = cached["processed_content"]
    elif isinstance(cached.get("removed_patterns"), list) and all(
        isinstance(item, str) for item in cached["removed_patterns"]
    ):
        cleaned["content"], _, _ = apply_removals(content, cached["removed_patterns"])
    else:
        return None

    cached["task_uids"] = sorted({task_uid, *cached.get("task_uids", [])})
    return cleaned


def clean_message(
    *,
    message: dict[str, Any],
    task_uid: str,
    message_index: int,
    constraints: list[dict[str, str]],
    cache: dict[str, Any],
    cache_lock: threading.Lock,
    key_locks: dict[str, threading.Lock],
    key_locks_lock: threading.Lock,
    model: str,
    base_url: str | None,
    api_key: str | None,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> tuple[dict[str, Any], str]:
    role = str(message.get("role", ""))
    content = message.get("content")
    if not isinstance(content, str) or not constraints:
        return copy.deepcopy(message), "skipped"

    key = cache_key(role=role, content=content, constraints=constraints)
    with key_locks_lock:
        key_lock = key_locks.setdefault(key, threading.Lock())

    # Serialize only identical prompt+constraint pairs. This preserves cache
    # reuse for repeated system prompts while allowing unrelated prompts to run
    # in parallel.
    with key_lock:
        with cache_lock:
            cached = cache["items"].get(key)
            if isinstance(cached, dict):
                cleaned = cleaned_from_cache(
                    message=message,
                    content=content,
                    cached=cached,
                    task_uid=task_uid,
                )
                if cleaned is None:
                    pass
                else:
                    return cleaned, "cache_hit"

        local_patterns, remaining_constraints = local_removals(content, constraints)
        locally_cleaned_content, applied_local_patterns, _ = apply_removals(content, local_patterns)
        if not remaining_constraints:
            with cache_lock:
                record_cache_item(
                    cache,
                    key=key,
                    role=role,
                    content=content,
                    constraints=constraints,
                    removed_patterns=applied_local_patterns,
                    unmatched_patterns=[],
                    model="local-pattern",
                    task_uid=task_uid,
                )
            cleaned = copy.deepcopy(message)
            cleaned["content"] = locally_cleaned_content
            return cleaned, "local_match"

        prompt = build_prompt(
            task_uid=task_uid,
            message_index=message_index,
            role=role,
            content=locally_cleaned_content,
            constraints=remaining_constraints,
        )
        raw = call_llm(
            model=model,
            base_url=base_url,
            api_key=api_key,
            prompt=prompt,
            max_tokens=max_tokens,
            timeout=timeout,
            retries=retries,
            sleep=sleep,
        )
        parsed = parse_llm_json(raw)
        removed_patterns = parsed.get("remove", parsed.get("removals", []))
        cleaned_content, applied_llm_patterns, unmatched_patterns = apply_removals(
            locally_cleaned_content,
            removed_patterns,
        )
        applied_patterns = [*applied_local_patterns, *applied_llm_patterns]

        with cache_lock:
            record_cache_item(
                cache,
                key=key,
                role=role,
                content=content,
                constraints=constraints,
                removed_patterns=applied_patterns,
                unmatched_patterns=unmatched_patterns,
                model=model,
                task_uid=task_uid,
            )

    cleaned = copy.deepcopy(message)
    cleaned["content"] = cleaned_content
    return cleaned, "llm_call"


def filter_task(
    task: dict[str, Any],
    *,
    cache: dict[str, Any],
    cache_lock: threading.Lock,
    key_locks: dict[str, threading.Lock],
    key_locks_lock: threading.Lock,
    model: str,
    base_url: str | None,
    api_key: str | None,
    max_tokens: int,
    timeout: float,
    retries: int,
    sleep: float,
) -> tuple[dict[str, Any], dict[str, int]]:
    filtered = copy.deepcopy(task)
    task_uid = str(task.get("mac_task_uid", task.get("id", "")))
    constraints = constraint_descs(task)
    stats = {"cache_hit": 0, "local_match": 0, "llm_call": 0, "skipped": 0, "error": 0}

    input_messages = task.get("input", [])
    if not isinstance(input_messages, list):
        stats["skipped"] += 1
        return filtered, stats

    cleaned_messages: list[Any] = []
    for index, message in enumerate(input_messages):
        if not isinstance(message, dict):
            cleaned_messages.append(copy.deepcopy(message))
            stats["skipped"] += 1
            continue
        cleaned, status = clean_message(
            message=message,
            task_uid=task_uid,
            message_index=index,
            constraints=constraints,
            cache=cache,
            cache_lock=cache_lock,
            key_locks=key_locks,
            key_locks_lock=key_locks_lock,
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_tokens=max_tokens,
            timeout=timeout,
            retries=retries,
            sleep=sleep,
        )
        stats[status] += 1
        cleaned_messages.append(cleaned)

    filtered["input"] = cleaned_messages
    return filtered, stats


def selected_tasks(
    tasks: list[dict[str, Any]],
    *,
    start: int,
    start_task: str | None,
    limit: int | None,
    only_task: set[str],
) -> list[tuple[int, dict[str, Any]]]:
    indexed = [
        (index, task)
        for index, task in enumerate(tasks)
        if isinstance(task, dict)
        and (not only_task or str(task.get("mac_task_uid", task.get("id", ""))) in only_task)
    ]
    if start_task:
        for offset, (_, task) in enumerate(indexed):
            if str(task.get("mac_task_uid", task.get("id", ""))) == start_task:
                indexed = indexed[offset:]
                break
        else:
            raise ValueError(f"--start-task not found after --only-task filtering: {start_task}")
    if start:
        indexed = indexed[start:]
    if limit is not None:
        indexed = indexed[:limit]
    return indexed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step1_focus.json"),
        help="Step-1 task dataset whose prompts should be cleaned.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step1_constraint_filtered.json"),
        help="Output task dataset with input prompts cleaned.",
    )
    parser.add_argument(
        "--prompt-lib",
        type=Path,
        default=Path("bench/MAC/mid_data/prompt_filter_lib.json"),
        help="Processed prompt cache/library.",
    )
    parser.add_argument("--env-file", type=Path, default=None, help="Optional .env file.")
    parser.add_argument(
        "--model",
        default=os.getenv("MAC_LLM_MODEL"),
        help="OpenAI-compatible model name. Defaults to MAC_LLM_MODEL.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL") or os.getenv("MAC_LLM_BASE_URL"),
        help="OpenAI-compatible base URL. Defaults to OPENAI_BASE_URL or MAC_LLM_BASE_URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="API key. Defaults to OPENAI_API_KEY.",
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=1, help="Number of tasks to process in parallel.")
    parser.add_argument("--start", type=int, default=0, help="Start offset after filtering --only-task.")
    parser.add_argument("--start-task", default=None, help="Start processing from this mac_task_uid.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of tasks.")
    parser.add_argument(
        "--only-task",
        action="append",
        default=[],
        help="Process only this mac_task_uid. Can be repeated.",
    )
    parser.add_argument(
        "--save-cache-every",
        type=int,
        default=10,
        help="Persist prompt library after this many processed tasks.",
    )
    return parser.parse_args()


def preparse_env_file() -> Path | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-file", type=Path, default=None)
    args, _ = parser.parse_known_args()
    return args.env_file


def output_base_tasks(*, output_path: Path, input_tasks: list[Any]) -> list[Any]:
    if not output_path.exists():
        return copy.deepcopy(input_tasks)

    existing = load_json(output_path)
    if not isinstance(existing, list) or len(existing) != len(input_tasks):
        return copy.deepcopy(input_tasks)
    return existing


def error_artifact_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".errors.json")


def main() -> int:
    load_env(preparse_env_file())
    args = parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)
    prompt_lib_path = resolve_path(args.prompt_lib)

    tasks = load_json(input_path)
    if not isinstance(tasks, list):
        raise ValueError(f"Expected top-level JSON array in {input_path}")

    cache = load_cache(prompt_lib_path)
    task_items = selected_tasks(
        tasks,
        start=args.start,
        start_task=args.start_task,
        limit=args.limit,
        only_task=set(args.only_task),
    )

    filtered_by_index: dict[int, dict[str, Any]] = {}
    totals = {"cache_hit": 0, "local_match": 0, "llm_call": 0, "skipped": 0, "error": 0}
    errors: list[dict[str, Any]] = []
    cache_lock = threading.Lock()
    key_locks: dict[str, threading.Lock] = {}
    key_locks_lock = threading.Lock()

    def process_task_item(item: tuple[int, dict[str, Any]]) -> tuple[int, str, dict[str, Any], dict[str, int]]:
        index, task = item
        task_uid = str(task.get("mac_task_uid", task.get("id", index)))
        try:
            filtered, stats = filter_task(
                task,
                cache=cache,
                cache_lock=cache_lock,
                key_locks=key_locks,
                key_locks_lock=key_locks_lock,
                model=args.model,
                base_url=args.base_url,
                api_key=args.api_key,
                max_tokens=args.max_tokens,
                timeout=args.timeout,
                retries=args.retries,
                sleep=args.sleep,
            )
            return index, task_uid, filtered, stats
        except Exception as exc:  # noqa: BLE001 - keep long batch runs moving.
            stats = {"cache_hit": 0, "local_match": 0, "llm_call": 0, "skipped": 0, "error": 1}
            filtered = copy.deepcopy(task)
            filtered["_prompt_filter_error"] = str(exc)
            return index, task_uid, filtered, stats

    workers = max(1, int(args.workers))
    if workers == 1:
        task_results = (process_task_item(item) for item in task_items)
    else:
        executor = ThreadPoolExecutor(max_workers=workers)
        futures = [executor.submit(process_task_item, item) for item in task_items]
        task_results = (future.result() for future in as_completed(futures))

    try:
        for processed_count, (index, task_uid, filtered, stats) in enumerate(task_results, start=1):
            filtered_by_index[index] = filtered
            for key, value in stats.items():
                totals[key] += value
            if stats.get("error"):
                errors.append(
                    {
                        "task_uid": task_uid,
                        "index": index,
                        "error": filtered.get("_prompt_filter_error"),
                    }
                )

            print(
                f"[{processed_count}/{len(task_items)}] {task_uid}: "
                f"llm={stats['llm_call']} cache={stats['cache_hit']} local={stats['local_match']} "
                f"skipped={stats['skipped']} errors={stats['error']}"
            )
            if args.save_cache_every and processed_count % args.save_cache_every == 0:
                with cache_lock:
                    write_json(prompt_lib_path, cache)
    finally:
        if workers > 1:
            executor.shutdown(wait=True)

    with cache_lock:
        write_json(prompt_lib_path, cache)
    base_tasks = output_base_tasks(output_path=output_path, input_tasks=tasks)
    output_tasks = []
    for index, task in enumerate(base_tasks):
        if index in filtered_by_index:
            output_tasks.append(filtered_by_index[index])
        else:
            output_tasks.append(copy.deepcopy(task))
    write_json(output_path, output_tasks)
    error_path = error_artifact_path(output_path)
    if errors:
        write_json(error_path, errors)
    elif error_path.exists():
        error_path.unlink()
    print(
        f"wrote {len(output_tasks)} task(s) to {output_path}; "
        f"llm_calls={totals['llm_call']}, cache_hits={totals['cache_hit']}, "
        f"local_matches={totals['local_match']}, skipped={totals['skipped']}, "
        f"errors={totals['error']}, "
        f"workers={workers}, prompt_lib={prompt_lib_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
