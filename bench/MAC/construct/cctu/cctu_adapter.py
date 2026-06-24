#!/usr/bin/env python3
"""Adapt CCTU tasks into MAC construct step-1 JSON.

Reads ``bench/CCTU/data/input_data.jsonl``, constraint-free system prompts, and
``bench/CCTU/check_code/`` validators, then writes a step-1 task array compatible
with ``rule_graph.py`` and ``constraint_merge.py``.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.cctu.bridge import (  # noqa: E402
    cctu_agent_name,
    cctu_difficulty,
    cctu_root,
    cctu_task_uid,
    first_message,
    load_cctu_samples,
    parse_cctu_tools,
)

DEFAULT_INPUT = Path("bench/CCTU/data/input_data.jsonl")
DEFAULT_CLEAN_PROMPTS = Path("bench/MAC/cctu/data/mac-cctu-system_prompt_constraint_free.json")
DEFAULT_OUTPUT = Path("bench/MAC/cctu/mid_data/eval_step1_cctu.json")


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_clean_prompts(path: Path) -> dict[str, str]:
    rows = load_json(path)
    if not isinstance(rows, list):
        raise ValueError(f"Expected top-level JSON array in {path}")
    return {str(row.get("id")): str(row.get("system_prompt") or "") for row in rows if isinstance(row, dict)}


def check_code_dir(task_id: str) -> Path:
    return cctu_root() / "check_code" / task_id


def check_code_path(task_id: str, index: int) -> Path | None:
    directory = check_code_dir(task_id)
    for suffix in (".json", ".py"):
        candidate = directory / f"check_constraint_{index}{suffix}"
        if candidate.exists():
            return candidate
    return None


def refine_constraint_from_py(content: str) -> str:
    match = re.search(
        r"refine_constraint:\s*(.+?)(?:\n\n|\nresponse_constraints|\Z)",
        content,
        flags=re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def refine_constraint_from_json(content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    refine = payload.get("refine_constraint")
    return refine.strip() if isinstance(refine, str) else ""


def constraint_desc(task_id: str, index: int, raw_desc: str) -> tuple[str, dict[str, Any]]:
    path = check_code_path(task_id, index)
    metadata: dict[str, Any] = {
        "check_code_stem": f"check_constraint_{index}",
        "check_path": None,
        "check_artifact_type": None,
    }
    if path is None:
        return raw_desc.strip(), metadata

    metadata["check_path"] = str(path.relative_to(cctu_root()))
    metadata["check_artifact_type"] = path.suffix.lstrip(".")
    content = path.read_text(encoding="utf-8")
    refine = refine_constraint_from_json(content) if path.suffix == ".json" else refine_constraint_from_py(content)
    return (refine or raw_desc).strip(), metadata


def user_task_summary(sample: dict[str, Any]) -> str:
    user_prompt = first_message(sample, "user").strip()
    marker = "Question:"
    if marker in user_prompt:
        question = user_prompt.split(marker, 1)[1].strip()
        if question:
            return question
    return user_prompt


def build_messages(
    sample: dict[str, Any],
    *,
    clean_system_prompt: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if clean_system_prompt:
        messages.append({"role": "system", "content": clean_system_prompt})
    user_prompt = first_message(sample, "user")
    if user_prompt:
        messages.append({"role": "user", "content": user_prompt})
    return messages


def constraint_records(sample: dict[str, Any], task_uid: str, task_id: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, raw in enumerate(sample.get("constraints_list") or []):
        if not isinstance(raw, list) or len(raw) < 3:
            continue
        primary, secondary, raw_desc = raw[:3]
        desc, checker_meta = constraint_desc(task_id, index, str(raw_desc))
        check_path = checker_meta.get("check_path")
        records.append(
            {
                "id": index,
                "mac_constraint_uid": f"{task_uid}-c{index + 1:04d}",
                "desc": desc,
                "cctu_raw_desc": str(raw_desc),
                "type": [str(primary), str(secondary)],
                "cctu_primary": str(primary),
                "cctu_secondary": str(secondary),
                "cctu_index": index,
                "evaluation": [
                    {
                        "type": "code",
                        "check_path": check_path,
                        "check_artifact_type": checker_meta.get("check_artifact_type"),
                    }
                ],
                **checker_meta,
            }
        )
    return records


def adapt_task(sample: dict[str, Any], *, clean_prompts: dict[str, str]) -> dict[str, Any]:
    sample_id = str(sample.get("id"))
    task_uid = cctu_task_uid(sample_id)
    clean_system = clean_prompts.get(sample_id, first_message(sample, "system"))
    constraints = constraint_records(sample, task_uid, sample_id)
    return {
        "id": sample_id,
        "cctu_id": sample_id,
        "mac_task_uid": task_uid,
        "agent_name": cctu_agent_name(sample_id),
        "task_level": cctu_difficulty(sample),
        "mac_task_summary": user_task_summary(sample),
        "domain_context": clean_system[:2000],
        "input": build_messages(sample, clean_system_prompt=clean_system),
        "original_input": copy.deepcopy(sample.get("messages") or []),
        "constraints": constraints,
        "constraints_list": copy.deepcopy(sample.get("constraints_list") or []),
        "tools": parse_cctu_tools(sample),
        "data_source": sample.get("data_source"),
        "answer": sample.get("answer"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--clean-prompts", type=Path, default=DEFAULT_CLEAN_PROMPTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=0, help="Maximum tasks to convert; 0 means all.")
    parser.add_argument("--offset", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = resolve_path(args.input)
    clean_prompts_path = resolve_path(args.clean_prompts)
    output_path = resolve_path(args.output)

    samples = load_cctu_samples(input_path)
    start = max(0, args.offset)
    end = None if not args.limit else start + args.limit
    samples = samples[start:end]

    clean_prompts = load_clean_prompts(clean_prompts_path)
    tasks = [adapt_task(sample, clean_prompts=clean_prompts) for sample in samples]

    payload = {
        "schema_version": "MACConstructStep1CCTUV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_input": str(input_path),
        "clean_prompts": str(clean_prompts_path),
        "summary": {
            "task_count": len(tasks),
            "constraint_count": sum(len(task.get("constraints") or []) for task in tasks),
            "avg_constraints_per_task": (
                sum(len(task.get("constraints") or []) for task in tasks) / len(tasks) if tasks else 0.0
            ),
        },
        "tasks": tasks,
    }
    write_json(output_path, tasks)
    meta_path = output_path.with_suffix(output_path.suffix + ".meta.json")
    write_json(meta_path, payload)
    print(
        f"wrote {len(tasks)} CCTU step-1 task(s) to {output_path}; "
        f"constraints={payload['summary']['constraint_count']}, meta={meta_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
