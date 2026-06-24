#!/usr/bin/env python3
"""Remove CCTU constraints from system prompts with an LLM.

Reads ``bench/CCTU/data/input_data.jsonl`` and writes
``bench/MAC/cctu/data/mac-cctu-system_prompt_constraint_free.json``.
Cache, error, and audit artifacts are stored under
``bench/MAC/cctu/cache_n_error/``.

Each LLM call receives the original system prompt plus the task's
``constraints_list`` and ``check_code/<id>/check_constraint_*`` artifacts.
Identical prompt+constraint combinations are cached and reused without another
LLM call.
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
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[4]
CACHE_VERSION = 1

DEFAULT_INPUT = Path("bench/CCTU/data/input_data.jsonl")
DEFAULT_OUTPUT = Path("bench/MAC/cctu/data/mac-cctu-system_prompt_constraint_free.json")
DEFAULT_CACHE_N_ERROR_DIR = Path("bench/MAC/cctu/cache_n_error")
DEFAULT_PROMPT_LIB = DEFAULT_CACHE_N_ERROR_DIR / f"{DEFAULT_OUTPUT.stem}.cache.json"
DEFAULT_ENV_FILE = Path("bench/.env")

SYSTEM_PROMPT = """
You clean CCTU benchmark system prompts.

You will receive:
- one CCTU system prompt
- the task's stored constraints_list
- any constraint checker code/configs for that task

Return a new system prompt with all constraint instructions removed. Constraints
are requirements about final answer format, length, wording, tool arguments,
tool ordering, interaction rounds, or similar evaluation rules.

Preserve everything else exactly as much as possible:
- Keep the agent role, task domain, tool-use instructions, and general task
  context.
- Keep wording, order, paragraph breaks, and punctuation unless removing a
  constraint requires a small cleanup.
- Do not add new instructions.
- Do not summarize or rewrite broadly.

If no listed constraint appears in the system prompt, return the original
system prompt unchanged.

Return valid JSON only, with this schema:
{"system_prompt": "cleaned system prompt"}
""".strip()


def load_json(path: Path, *, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return copy.deepcopy(default)
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_number}")
            rows.append(payload)
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def load_env(env_file: Path | None) -> None:
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


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
                temperature=0.3,
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


def parse_llm_json(text: str) -> dict[str, str]:
    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        if match:
            stripped = match.group(1).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON root must be an object")
    system_prompt = payload.get("system_prompt")
    if not isinstance(system_prompt, str):
        raise ValueError("LLM JSON must contain string field 'system_prompt'")
    return {"system_prompt": system_prompt}


def sample_system_prompt(sample: dict[str, Any]) -> str:
    messages = sample.get("messages", [])
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "system":
            continue
        content = message.get("content")
        return content if isinstance(content, str) else ""
    return ""


def constraint_artifacts(sample: dict[str, Any], *, input_path: Path) -> list[dict[str, str]]:
    task_id = str(sample.get("id", ""))
    validators_dir = input_path.parent.parent / "check_code" / task_id
    if not validators_dir.exists():
        return []

    artifacts: list[dict[str, str]] = []
    for path in sorted(validators_dir.glob("check_constraint_*")):
        if path.suffix not in {".py", ".json"}:
            continue
        artifacts.append(
            {
                "path": str(path.relative_to(input_path.parent.parent)),
                "content": path.read_text(encoding="utf-8"),
            }
        )
    return artifacts


def constraint_payload(sample: dict[str, Any], *, input_path: Path) -> dict[str, Any]:
    return {
        "constraints_list": sample.get("constraints_list", []),
        "constraint_checkers": constraint_artifacts(sample, input_path=input_path),
    }


def cache_key(*, system_prompt: str, constraints: dict[str, Any]) -> str:
    return sha256_text(
        stable_json(
            {
                "mode": "cctu-system-prompt-v1",
                "system_prompt": system_prompt,
                "constraints": constraints,
            }
        )
    )


def record_cache_item(
    cache: dict[str, Any],
    *,
    key: str,
    system_prompt: str,
    constraints: dict[str, Any],
    processed_system_prompt: str,
    model: str,
    task_id: str,
) -> None:
    existing_task_ids = cache["items"].get(key, {}).get("task_ids", [])
    cache["items"][key] = {
        "mode": "cctu-system-prompt",
        "system_prompt_hash": sha256_text(system_prompt),
        "constraints_hash": sha256_text(stable_json(constraints)),
        "processed_system_prompt": processed_system_prompt,
        "model": model,
        "task_ids": sorted({task_id, *existing_task_ids}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache["updated_at"] = datetime.now(timezone.utc).isoformat()


def build_prompt(*, task_id: str, system_prompt: str, constraints: dict[str, Any]) -> str:
    payload = {
        "task_id": task_id,
        "system_prompt": system_prompt,
        "constraints": constraints,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def clean_system_prompt(
    *,
    sample: dict[str, Any],
    input_path: Path,
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
    task_id = str(sample.get("id", ""))
    system_prompt = sample_system_prompt(sample)
    if not system_prompt:
        return {"id": sample.get("id"), "system_prompt": ""}, "skipped"

    constraints = constraint_payload(sample, input_path=input_path)
    key = cache_key(system_prompt=system_prompt, constraints=constraints)
    with key_locks_lock:
        key_lock = key_locks.setdefault(key, threading.Lock())

    with key_lock:
        with cache_lock:
            cached = cache["items"].get(key)
            if isinstance(cached, dict) and isinstance(cached.get("processed_system_prompt"), str):
                cached["task_ids"] = sorted({task_id, *cached.get("task_ids", [])})
                return {"id": sample.get("id"), "system_prompt": cached["processed_system_prompt"]}, "cache_hit"

        raw = call_llm(
            model=model,
            base_url=base_url,
            api_key=api_key,
            prompt=build_prompt(
                task_id=task_id,
                system_prompt=system_prompt,
                constraints=constraints,
            ),
            max_tokens=max_tokens,
            timeout=timeout,
            retries=retries,
            sleep=sleep,
        )
        parsed = parse_llm_json(raw)
        processed_system_prompt = parsed["system_prompt"]

        with cache_lock:
            record_cache_item(
                cache,
                key=key,
                system_prompt=system_prompt,
                constraints=constraints,
                processed_system_prompt=processed_system_prompt,
                model=model,
                task_id=task_id,
            )

    return {"id": sample.get("id"), "system_prompt": processed_system_prompt}, "llm_call"


def selected_samples(
    samples: list[dict[str, Any]],
    *,
    start: int,
    start_task: str | None,
    limit: int | None,
    only_task: set[str],
) -> list[tuple[int, dict[str, Any]]]:
    indexed = [
        (index, sample)
        for index, sample in enumerate(samples)
        if not only_task or str(sample.get("id", "")) in only_task
    ]
    if start_task:
        for offset, (_, sample) in enumerate(indexed):
            if str(sample.get("id", "")) == start_task:
                indexed = indexed[offset:]
                break
        else:
            raise ValueError(f"--start-task not found after --only-task filtering: {start_task}")
    if start:
        indexed = indexed[start:]
    if limit is not None:
        indexed = indexed[:limit]
    return indexed


def cache_n_error_dir(output_path: Path) -> Path:
    return output_path.parent / "cache_n_error"


def default_prompt_lib_path(output_path: Path) -> Path:
    return cache_n_error_dir(output_path) / f"{output_path.stem}.cache.json"


def legacy_prompt_lib_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".cache.json")


def resolve_prompt_lib_path(prompt_lib_path: Path, *, output_path: Path) -> Path:
    if prompt_lib_path.exists():
        return prompt_lib_path
    legacy = legacy_prompt_lib_path(output_path)
    if legacy.exists():
        return legacy
    return prompt_lib_path


def error_artifact_path(output_path: Path) -> Path:
    return cache_n_error_dir(output_path) / f"{output_path.name}.errors.json"


def audit_report_path(output_path: Path) -> Path:
    return cache_n_error_dir(output_path) / f"{output_path.name}.audit.json"


STRUCTURAL_LEAK_MARKERS = [
    "Interaction Round Limit and Forced Termination",
    "maximum 20 interaction rounds",
    "CRITICAL STOP PROTOCOL: If you reach",
    "At most 20 including final answer",
    "valid JSON object with a single key",
    "valid JSON object with the company name",
    "strictly in Markdown syntax",
    "Response Length must be between",
    "must be at most 10 words",
    "must be between 5 and 10 words",
    "may be used at most once",
    "Maximum 2 tool calls per task",
    "At most 10 tool calls",
]


def normalize_match_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def constraint_signals(sample: dict[str, Any], *, input_path: Path) -> list[str]:
    signals: list[str] = []
    seen: set[str] = set()

    def add_signal(value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            return
        key = normalize_match_text(cleaned)
        if key in seen:
            return
        seen.add(key)
        signals.append(cleaned)

    for item in sample.get("constraints_list") or []:
        if isinstance(item, list) and len(item) >= 3 and isinstance(item[2], str):
            add_signal(item[2])

    for artifact in constraint_artifacts(sample, input_path=input_path):
        content = artifact["content"]
        if artifact["path"].endswith(".json"):
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                refine = payload.get("refine_constraint")
                if isinstance(refine, str):
                    add_signal(refine)
        elif artifact["path"].endswith(".py"):
            match = re.search(
                r"refine_constraint:\s*(.+?)(?:\n\n|\nresponse_constraints|\Z)",
                content,
                flags=re.DOTALL,
            )
            if match:
                add_signal(match.group(1))

    return signals


def signal_present(text: str, signal: str) -> bool:
    haystack = normalize_match_text(text)
    needle = normalize_match_text(signal)
    if not needle:
        return False
    if needle in haystack:
        return True
    if len(needle) >= 48:
        return needle[:48] in haystack
    return False


def audit_task_leaks(
    *,
    sample: dict[str, Any],
    filtered_prompt: str,
    input_path: Path,
) -> list[dict[str, str]]:
    original_prompt = sample_system_prompt(sample)
    leaks: list[dict[str, str]] = []

    for signal in constraint_signals(sample, input_path=input_path):
        if signal_present(original_prompt, signal) and signal_present(filtered_prompt, signal):
            leaks.append({"type": "constraint_signal", "signal": signal[:240]})

    for marker in STRUCTURAL_LEAK_MARKERS:
        if marker.lower() in original_prompt.lower() and marker.lower() in filtered_prompt.lower():
            leaks.append({"type": "structural_marker", "signal": marker})

    return leaks


def audit_filtered_prompts(
    *,
    input_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    samples = load_jsonl(input_path)
    if not output_path.exists():
        raise FileNotFoundError(f"Filtered prompt output is missing: {output_path}")

    filtered_rows = load_json(output_path)
    if not isinstance(filtered_rows, list):
        raise ValueError(f"Expected top-level JSON array in {output_path}")

    filtered_by_id = {
        str(row.get("id")): str(row.get("system_prompt") or "")
        for row in filtered_rows
        if isinstance(row, dict)
    }

    task_reports: list[dict[str, Any]] = []
    for sample in samples:
        task_id = str(sample.get("id"))
        filtered_prompt = filtered_by_id.get(task_id, "")
        if not filtered_prompt:
            task_reports.append(
                {
                    "id": task_id,
                    "status": "missing_output",
                    "leaks": [{"type": "missing_output", "signal": "filtered system_prompt not found"}],
                }
            )
            continue

        leaks = audit_task_leaks(
            sample=sample,
            filtered_prompt=filtered_prompt,
            input_path=input_path,
        )
        task_reports.append(
            {
                "id": task_id,
                "status": "leak" if leaks else "ok",
                "leaks": leaks,
            }
        )

    leaking = [report for report in task_reports if report["status"] != "ok"]
    report = {
        "input": str(input_path),
        "output": str(output_path),
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "task_count": len(task_reports),
        "ok_count": sum(1 for report in task_reports if report["status"] == "ok"),
        "leak_count": sum(1 for report in task_reports if report["status"] == "leak"),
        "missing_count": sum(1 for report in task_reports if report["status"] == "missing_output"),
        "leaking_tasks": leaking,
    }
    return report


def run_audit(*, input_path: Path, output_path: Path) -> int:
    report = audit_filtered_prompts(input_path=input_path, output_path=output_path)
    audit_path = audit_report_path(output_path)
    write_json(audit_path, report)

    print(
        f"audit complete: ok={report['ok_count']}/{report['task_count']} "
        f"leaks={report['leak_count']} missing={report['missing_count']} "
        f"report={audit_path}"
    )
    if report["leak_count"] or report["missing_count"]:
        for task in report["leaking_tasks"][:10]:
            signals = ", ".join(item["signal"][:80] for item in task.get("leaks", [])[:3])
            print(f"  id={task['id']} status={task['status']}: {signals}")
        if len(report["leaking_tasks"]) > 10:
            print(f"  ... and {len(report['leaking_tasks']) - 10} more")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="CCTU input JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Filtered system prompt JSON output.")
    parser.add_argument(
        "--prompt-lib",
        type=Path,
        default=None,
        help="Processed prompt cache/library. Defaults to cache_n_error/<output-stem>.cache.json.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="Env file with LLM_MODEL / LLM_BASE_URL / LLM_API_KEY. Defaults to bench/.env.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="OpenAI-compatible model name. Defaults to MAC_LLM_MODEL or LLM_MODEL.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible base URL. Defaults to OPENAI_BASE_URL, MAC_LLM_BASE_URL, or LLM_BASE_URL.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key. Defaults to OPENAI_API_KEY or LLM_API_KEY.",
    )
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--workers", type=int, default=1, help="Number of tasks to process in parallel.")
    parser.add_argument("--start", type=int, default=0, help="Start offset after filtering --only-task.")
    parser.add_argument("--start-task", default=None, help="Start processing from this CCTU task id.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of tasks.")
    parser.add_argument(
        "--only-task",
        action="append",
        default=[],
        help="Process only this CCTU id. Can be repeated.",
    )
    parser.add_argument(
        "--save-cache-every",
        type=int,
        default=10,
        help="Persist prompt library after this many processed tasks.",
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Skip LLM filtering and only audit an existing system_prompt_constraint_free.json.",
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Skip post-run constraint leak audit.",
    )
    return parser.parse_args()


def preparse_env_file() -> Path | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args, _ = parser.parse_known_args()
    return args.env_file


def main() -> int:
    load_env(preparse_env_file())
    args = parse_args()

    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output)

    if args.audit_only:
        return run_audit(input_path=input_path, output_path=output_path)

    resolve_llm_config(args)

    prompt_lib_path = resolve_path(args.prompt_lib or default_prompt_lib_path(output_path))
    prompt_lib_path = resolve_prompt_lib_path(prompt_lib_path, output_path=output_path)
    samples = load_jsonl(input_path)
    task_items = selected_samples(
        samples,
        start=args.start,
        start_task=args.start_task,
        limit=args.limit,
        only_task=set(args.only_task),
    )

    cache = load_cache(prompt_lib_path)
    cache_lock = threading.Lock()
    key_locks: dict[str, threading.Lock] = {}
    key_locks_lock = threading.Lock()
    filtered_by_index: dict[int, dict[str, Any]] = {}
    totals = {"cache_hit": 0, "llm_call": 0, "skipped": 0, "error": 0}
    errors: list[dict[str, Any]] = []

    def process_task_item(item: tuple[int, dict[str, Any]]) -> tuple[int, str, dict[str, Any], dict[str, int]]:
        index, sample = item
        task_id = str(sample.get("id", index))
        try:
            filtered, status = clean_system_prompt(
                sample=sample,
                input_path=input_path,
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
            stats = {"cache_hit": 0, "llm_call": 0, "skipped": 0, "error": 0}
            stats[status] += 1
            return index, task_id, filtered, stats
        except Exception as exc:  # noqa: BLE001 - keep long batch runs moving.
            stats = {"cache_hit": 0, "llm_call": 0, "skipped": 0, "error": 1}
            return (
                index,
                task_id,
                {
                    "id": sample.get("id"),
                    "system_prompt": sample_system_prompt(sample),
                    "_prompt_filter_error": str(exc),
                },
                stats,
            )

    workers = max(1, int(args.workers))
    executor: ThreadPoolExecutor | None = None
    progress = tqdm(total=len(task_items), desc="CCTU prompt filter", unit="task")

    try:
        if workers == 1:
            task_results = (process_task_item(item) for item in task_items)
        else:
            executor = ThreadPoolExecutor(max_workers=workers)
            futures = [executor.submit(process_task_item, item) for item in task_items]
            task_results = (future.result() for future in as_completed(futures))

        for index, task_id, filtered, stats in task_results:
            filtered_by_index[index] = filtered
            for key, value in stats.items():
                totals[key] += value
            if stats.get("error"):
                errors.append(
                    {
                        "id": task_id,
                        "index": index,
                        "error": filtered.get("_prompt_filter_error"),
                    }
                )

            progress.update(1)
            progress.set_postfix(
                id=task_id,
                llm=totals["llm_call"],
                cache=totals["cache_hit"],
                skip=totals["skipped"],
                err=totals["error"],
                refresh=False,
            )
            if args.save_cache_every and progress.n % args.save_cache_every == 0:
                with cache_lock:
                    write_json(prompt_lib_path, cache)
    finally:
        progress.close()
        if executor is not None:
            executor.shutdown(wait=True)

    with cache_lock:
        write_json(prompt_lib_path, cache)

    output_rows = [
        {"id": filtered_by_index[index].get("id"), "system_prompt": filtered_by_index[index].get("system_prompt", "")}
        for index, _ in task_items
    ]
    write_json(output_path, output_rows)
    error_path = error_artifact_path(output_path)
    if errors:
        write_json(error_path, errors)
    elif error_path.exists():
        error_path.unlink()

    print(
        f"wrote {len(output_rows)} CCTU system prompt(s) to {output_path}; "
        f"llm_calls={totals['llm_call']}, cache_hits={totals['cache_hit']}, "
        f"skipped={totals['skipped']}, errors={totals['error']}, "
        f"workers={workers}, prompt_lib={prompt_lib_path}"
    )

    if args.skip_audit:
        return 0
    return run_audit(input_path=input_path, output_path=output_path)


if __name__ == "__main__":
    raise SystemExit(main())
