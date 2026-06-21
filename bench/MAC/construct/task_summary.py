#!/usr/bin/env python3
"""Summarize MAC-Bench tasks into a short what-is-the-task description.

Reads AgentIF-style tasks, strips known constraint text from system/user
messages, and asks an LLM to summarize the task domain and deliverable without
output-format or procedure rules. Writes `mac_task_summary` onto each task.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

SYSTEM_PROMPT = """
You summarize benchmark tasks for MACBench.

Input:
- `system` and `user` are the task chat messages after known constraint texts
  were removed mechanically.
- `constraints` lists those removed constraint descriptions for reference only.
  Do not restate them in the summary.

Write a short summary of WHAT the task is:
- agent domain and role
- user situation or inputs
- the substantive deliverable or goal

Do NOT include:
- output formatting rules (length, headings, XML/markdown bans, sentence counts)
- tone/style/wording requirements
- step-by-step instructions for how to complete the task
- anything that duplicates the removed constraints

Return valid JSON only. Do not use markdown fences.

{
  "task_summary": "2-4 sentences describing the task itself"
}
""".strip()


class SummaryError(RuntimeError):
    """Raised when a task summary cannot be trusted."""


def load_env() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    env_file = repo_root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("bench/MAC/mid_data/eval_step1_tmp.json"),
        help="Step-1 dataset to annotate with mac_task_summary.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path. Defaults to --input (in-place update).",
    )
    parser.add_argument("--offset", type=int, default=0, help="Start at this task offset.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N tasks.")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip tasks that already have a non-empty mac_task_summary.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("MAC_LLM_MODEL"),
        help="OpenAI-compatible model name. Defaults to MAC_LLM_MODEL.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPENAI_BASE_URL"),
        help="OpenAI-compatible base URL. Defaults to OPENAI_BASE_URL.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="API key. Defaults to OPENAI_API_KEY.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call an LLM; write heuristic placeholder summaries.",
    )
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1, help="Parallel task workers.")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Base seconds to sleep between retry attempts.",
    )
    parser.add_argument(
        "--max-user-chars",
        type=int,
        default=12000,
        help="Truncate cleaned user text beyond this many characters.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def selected_items(data: list[dict[str, Any]], offset: int, limit: int | None) -> list[dict[str, Any]]:
    if offset < 0:
        raise ValueError("--offset must be non-negative")
    if limit is not None and limit < 0:
        raise ValueError("--limit must be non-negative")
    end = None if limit is None else offset + limit
    return data[offset:end]


def extract_messages(task: dict[str, Any]) -> tuple[str, str]:
    system_parts: list[str] = []
    user_parts: list[str] = []
    for message in task.get("input", []):
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
        elif role == "user":
            user_parts.append(content)
    return "\n".join(system_parts).strip(), "\n".join(user_parts).strip()


def constraint_descriptions(task: dict[str, Any]) -> list[str]:
    descriptions: list[str] = []
    for constraint in task.get("constraints", []):
        if not isinstance(constraint, dict):
            continue
        desc = str(constraint.get("desc", "")).strip()
        if desc:
            descriptions.append(desc)
    return descriptions


def normalize_for_match(text: str) -> str:
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def constraint_variants(desc: str) -> list[str]:
    variants = {desc, normalize_for_match(desc)}
    for value in list(variants):
        if value.endswith("."):
            variants.add(value[:-1].strip())
        if value.endswith("'."):
            variants.add(value[:-2].strip() + "'")
    return [variant for variant in variants if variant]


def strip_constraint_texts(text: str, descriptions: list[str]) -> str:
    if not text:
        return ""
    result = text
    variants: set[str] = set()
    for desc in descriptions:
        variants.update(constraint_variants(desc))
    for variant in sorted(variants, key=len, reverse=True):
        if len(variant) < 4:
            continue
        result = re.sub(re.escape(variant), "", result, flags=re.IGNORECASE)
    result = re.sub(r"[ \t]+\n", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    return result.strip()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def build_user_prompt(
    task: dict[str, Any],
    *,
    cleaned_system: str,
    cleaned_user: str,
    constraints: list[str],
) -> str:
    payload = {
        "mac_task_uid": task.get("mac_task_uid"),
        "agent_name": task.get("agent_name"),
        "system": cleaned_system,
        "user": cleaned_user,
        "constraints": constraints,
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
        raise RuntimeError("openai package is required for live task summarization") from exc

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
                temperature=0.2,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001 - CLI should retry transport/provider errors.
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
        raise SummaryError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SummaryError("LLM JSON root must be an object")
    return payload


def first_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return parts[0].strip()


def fallback_summary(task: dict[str, Any], *, cleaned_system: str, cleaned_user: str) -> str:
    agent = str(task.get("agent_name", "unknown agent"))
    role = first_sentence(cleaned_system) or first_sentence(cleaned_user) or "No prompt text available."
    user_hint = first_sentence(cleaned_user.splitlines()[0] if cleaned_user else "")
    parts = [f"The task uses agent `{agent}`."]
    if role:
        parts.append(role)
    if user_hint and user_hint != role:
        parts.append(f"User context begins with: {user_hint}")
    return " ".join(parts)


def summarize_task(task: dict[str, Any], *, args: argparse.Namespace) -> str:
    system_text, user_text = extract_messages(task)
    constraints = constraint_descriptions(task)
    cleaned_system = strip_constraint_texts(system_text, constraints)
    cleaned_user = truncate_text(
        strip_constraint_texts(user_text, constraints),
        args.max_user_chars,
    )
    prompt = build_user_prompt(
        task,
        cleaned_system=cleaned_system,
        cleaned_user=cleaned_user,
        constraints=constraints,
    )

    if args.dry_run:
        return fallback_summary(task, cleaned_system=cleaned_system, cleaned_user=cleaned_user)

    response_text = call_llm(
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        prompt=prompt,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        retries=args.retries,
        sleep=args.sleep,
    )
    payload = parse_llm_json(response_text)
    summary = str(payload.get("task_summary", "")).strip()
    if not summary:
        raise SummaryError("Missing non-empty task_summary field")
    return summary


def should_skip(task: dict[str, Any], *, skip_existing: bool) -> bool:
    if not skip_existing:
        return False
    existing = task.get("mac_task_summary")
    return isinstance(existing, str) and bool(existing.strip())


def process_task(
    *,
    task_number: int,
    total_tasks: int,
    task: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[bool, bool]:
    uid = task.get("mac_task_uid", task.get("id"))
    print(
        f"processing task {task_number}/{total_tasks} uid={uid} agent={task.get('agent_name')}",
        flush=True,
    )
    if should_skip(task, skip_existing=args.skip_existing):
        print(f"skipped task {task_number}/{total_tasks} uid={uid} (existing summary)", flush=True)
        return False, False

    try:
        task["mac_task_summary"] = summarize_task(task, args=args)
        print(f"finished task {task_number}/{total_tasks} uid={uid}", flush=True)
        return True, False
    except Exception as exc:  # noqa: BLE001 - keep batch summarization moving.
        system_text, user_text = extract_messages(task)
        constraints = constraint_descriptions(task)
        cleaned_system = strip_constraint_texts(system_text, constraints)
        cleaned_user = strip_constraint_texts(user_text, constraints)
        task["mac_task_summary"] = fallback_summary(
            task,
            cleaned_system=cleaned_system,
            cleaned_user=cleaned_user,
        )
        print(f"task uid={uid} failed, used fallback: {exc}", file=sys.stderr)
        return True, True


def main() -> int:
    load_env()
    args = parse_args()
    input_path = resolve_path(args.input)
    output_path = resolve_path(args.output or args.input)
    data = load_json(input_path)
    if not isinstance(data, list):
        raise ValueError(f"Expected top-level JSON array in {input_path}")

    selected = selected_items(data, args.offset, args.limit)
    total = len(selected)
    workers = max(1, int(args.workers))
    updated = 0
    failed = 0

    if workers == 1:
        for index, task in enumerate(selected, start=1):
            changed, task_failed = process_task(
                task_number=index,
                total_tasks=total,
                task=task,
                args=args,
            )
            updated += int(changed)
            failed += int(task_failed)
    else:
        indexed_tasks = list(enumerate(selected, start=1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    process_task,
                    task_number=index,
                    total_tasks=total,
                    task=task,
                    args=args,
                ): index
                for index, task in indexed_tasks
            }
            for future in as_completed(futures):
                changed, task_failed = future.result()
                updated += int(changed)
                failed += int(task_failed)

    write_json(output_path, data)
    print(
        f"wrote {len(data)} task(s) to {output_path}; "
        f"processed={total}, updated={updated}, failed={failed}, dry_run={args.dry_run}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
