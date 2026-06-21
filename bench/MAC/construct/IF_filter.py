#!/usr/bin/env python3
"""Filter AgentIF constraints for MAC-Bench preference/code candidates.

The script reads an AgentIF-style dataset, sends each sample's LLM-evaluated
constraints to an OpenAI-compatible model, and asks whether each constraint is
already a user-specified preference. After all model outputs are applied, it
writes only tasks that contain at least one selected constraint:

- an LLM-evaluated constraint judged to be a user preference; or
- a constraint with code-based evaluation.

The output keeps original constraint IDs untouched; duplicate IDs are
disambiguated with array indexes in the LLM prompt.
"""

from __future__ import annotations

import argparse
import copy
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
Decide whether each AgentIF constraint is a user-specified preference.

A preference means the user chose one acceptable behavior among multiple valid
answers, and that choice appears in the user prompt. It is not a preference just
because it could be rewritten as one.

Rules:
- If the constraint appears in the system prompt, mark it false.
- If it does not appear in the user prompt, mark it false.
- If it is a task requirement, tool/protocol rule, role instruction, safety rule,
  or hard requirement, mark it false.
- Mark true only when the current constraint itself expresses a user's optional
  preference or choice.

Input:
- `input` is the chat prompt for one AgentIF task.
- `system` messages define the agent/application behavior.
- `user` messages contain the user's request and any user-stated choices.
- `constraints` are candidate rules extracted from that task; judge only these
  constraints, using `constraint_index` to identify them.

Return valid JSON only:

{
  "preference_annotations": [
    {
      "constraint_index": 0,
      "is_preference": true,
      "reason": "brief reason"
    }
  ]
}

Annotate every supplied constraint exactly once. Use an empty reason when
`is_preference=false`. Prefer false when uncertain.
""".strip()


class ExtractionError(RuntimeError):
    """Raised when a sample-level annotation cannot be trusted."""


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
        default=Path("bench/MAC/data/eval_filter_example.json"),
        help="Filtered AgentIF dataset to annotate.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("bench/MAC/data/eval_preference_or_code_filter.json"),
        help="Filtered dataset output path.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Annotate at most N samples.")
    parser.add_argument("--offset", type=int, default=0, help="Start annotating at this sample offset.")
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
        help="Do not call an LLM; annotate selected constraints as manual_review placeholders.",
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1, help="Number of samples to annotate in parallel.")
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Base seconds to sleep between retry attempts.",
    )
    return parser.parse_args()


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


def evaluation_types(constraint: dict[str, Any]) -> set[str]:
    evaluations = constraint.get("evaluation", [])
    if not isinstance(evaluations, list):
        return set()
    return {
        str(evaluation.get("type"))
        for evaluation in evaluations
        if isinstance(evaluation, dict) and evaluation.get("type")
    }


def is_llm_eval_constraint(constraint: dict[str, Any]) -> bool:
    return "llm" in evaluation_types(constraint)


def is_code_based_evaluation(constraint: dict[str, Any]) -> bool:
    return "code" in evaluation_types(constraint)


def constraints_for_prompt(sample: dict[str, Any]) -> list[dict[str, Any]]:
    prompt_constraints: list[dict[str, Any]] = []
    for index, constraint in enumerate(sample.get("constraints", [])):
        if not isinstance(constraint, dict) or not is_llm_eval_constraint(constraint):
            continue
        prompt_constraint = {
            "constraint_index": index,
            "constraint_id": constraint.get("id"),
            "desc": constraint.get("desc"),
            "dimension": constraint.get("dimension"),
            "is_meta": constraint.get("is_meta"),
            "meta_type": constraint.get("meta_type"),
            "type": constraint.get("type"),
            "other_info": constraint.get("other_info", {}),
            "evaluation_types": sorted(evaluation_types(constraint)),
        }
        prompt_constraints.append(prompt_constraint)
    return prompt_constraints


def build_user_prompt(sample: dict[str, Any], constraints: list[dict[str, Any]]) -> str:
    payload = {
        "sample_id": sample.get("id"),
        "agent_name": sample.get("agent_name"),
        "input": sample.get("input", []),
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
        raise RuntimeError("openai package is required for live extraction") from exc

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
        except Exception as exc:  # noqa: BLE001 - CLI should retry all transport/provider errors.
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
        raise ExtractionError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ExtractionError("LLM JSON root must be an object")
    return payload


def normalize_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return default


def validate_annotations(
    payload: dict[str, Any],
    expected_indexes: set[int],
) -> dict[int, dict[str, Any]]:
    annotations = payload.get("preference_annotations")
    if not isinstance(annotations, list):
        raise ExtractionError("Missing list field: preference_annotations")

    normalized: dict[int, dict[str, Any]] = {}
    for raw_annotation in annotations:
        if not isinstance(raw_annotation, dict):
            continue
        try:
            index = int(raw_annotation.get("constraint_index"))
        except (TypeError, ValueError):
            continue
        if index not in expected_indexes or index in normalized:
            continue

        raw_is_preference = raw_annotation.get(
            "is_preference",
            raw_annotation.get("can_be_rewritten_as_preference"),
        )
        is_preference = normalize_bool(raw_is_preference, default=False)
        reason = str(raw_annotation.get("reason", ""))[:500]
        if not is_preference:
            reason = ""

        normalized[index] = {
            "is_preference": is_preference,
            "reason": reason,
        }

    missing = expected_indexes - set(normalized)
    if missing:
        missing_text = ", ".join(str(index) for index in sorted(missing))
        raise ExtractionError(f"Missing annotations for constraint_index: {missing_text}")

    return normalized


def fallback_annotations(
    indexes: set[int],
    *,
    reason: str,
) -> dict[int, dict[str, Any]]:
    return {
        index: {
            "is_preference": False,
            "reason": reason[:500],
        }
        for index in indexes
    }


def dry_run_annotations(
    constraints: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    indexes = {int(constraint["constraint_index"]) for constraint in constraints}
    return fallback_annotations(
        indexes,
        reason="Dry run placeholder; no LLM annotation was requested.",
    )


def apply_annotations(
    sample: dict[str, Any],
    annotations: dict[int, dict[str, Any]],
) -> None:
    constraints = sample.get("constraints", [])
    for index, annotation in annotations.items():
        constraints[index].update(annotation)


def annotate_sample(
    sample: dict[str, Any],
    *,
    args: argparse.Namespace,
) -> bool:
    constraints = constraints_for_prompt(sample)
    if not constraints:
        return False

    expected_indexes = {int(constraint["constraint_index"]) for constraint in constraints}
    prompt = build_user_prompt(sample, constraints)

    if args.dry_run:
        apply_annotations(sample, dry_run_annotations(constraints))
        return True

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

    try:
        payload = parse_llm_json(response_text)
        annotations = validate_annotations(payload, expected_indexes)
    except ExtractionError as exc:
        annotations = fallback_annotations(expected_indexes, reason=str(exc))

    apply_annotations(sample, annotations)
    return True


def process_sample(
    *,
    sample_number: int,
    total_samples: int,
    sample: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[bool, bool]:
    print(
        f"processing sample {sample_number}/{total_samples} "
        f"id={sample.get('id')} agent={sample.get('agent_name')}",
        flush=True,
    )
    try:
        annotated = annotate_sample(sample, args=args)
        print(
            f"finished sample {sample_number}/{total_samples} "
            f"id={sample.get('id')}",
            flush=True,
        )
        return annotated, False
    except Exception as exc:  # noqa: BLE001 - keep batch extraction moving.
        indexes = {
            index
            for index, constraint in enumerate(sample.get("constraints", []))
            if isinstance(constraint, dict) and is_llm_eval_constraint(constraint)
        }
        apply_annotations(
            sample,
            fallback_annotations(
                indexes,
                reason=f"sample annotation failed: {exc}",
            ),
        )
        print(f"sample_id={sample.get('id')} failed: {exc}", file=sys.stderr)
        return False, True


def is_preference_candidate(constraint: dict[str, Any]) -> bool:
    return normalize_bool(
        constraint.get("is_preference", constraint.get("can_be_rewritten_as_preference")),
        default=False,
    )


def selection_reasons(constraint: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if is_preference_candidate(constraint):
        reasons.append("preference_candidate")
    if is_code_based_evaluation(constraint):
        reasons.append("code_based_evaluation")
    return reasons


def filter_selected_tasks(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for sample in data:
        constraints = sample.get("constraints", [])
        if not isinstance(constraints, list):
            continue

        selected_constraints: list[dict[str, Any]] = []
        llm_eval_count = 0
        code_eval_count = 0
        preference_candidate_count = 0

        for constraint in constraints:
            if not isinstance(constraint, dict):
                continue
            if is_llm_eval_constraint(constraint):
                llm_eval_count += 1
            if is_code_based_evaluation(constraint):
                code_eval_count += 1
            if is_preference_candidate(constraint):
                preference_candidate_count += 1

            reasons = selection_reasons(constraint)
            if not reasons:
                continue
            selected_constraint = copy.deepcopy(constraint)
            selected_constraint["mac_bench_filter_reasons"] = reasons
            selected_constraints.append(selected_constraint)

        if not selected_constraints:
            continue

        selected_sample = copy.deepcopy(sample)
        selected_sample["constraints"] = selected_constraints
        selected_sample["mac_bench_filter_summary"] = {
            "original_constraint_count": len(constraints),
            "selected_constraint_count": len(selected_constraints),
            "llm_eval_constraint_count": llm_eval_count,
            "code_eval_constraint_count": code_eval_count,
            "preference_candidate_count": preference_candidate_count,
            "selection_rule": (
                "constraint is kept if is_preference=true "
                "or evaluation includes type=code"
            ),
        }
        filtered.append(selected_sample)
    return filtered


def main() -> int:
    load_env()
    args = parse_args()
    data = load_json(args.input)
    if not isinstance(data, list):
        raise ValueError(f"Expected top-level JSON array in {args.input}")

    output_data = copy.deepcopy(data)
    selected_data = selected_items(output_data, args.offset, args.limit)
    changed = 0
    failures = 0

    workers = max(1, int(args.workers))
    if workers == 1:
        for sample_number, sample in enumerate(selected_data, start=1):
            annotated, failed = process_sample(
                sample_number=sample_number,
                total_samples=len(selected_data),
                sample=sample,
                args=args,
            )
            changed += int(annotated)
            failures += int(failed)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    process_sample,
                    sample_number=sample_number,
                    total_samples=len(selected_data),
                    sample=sample,
                    args=args,
                )
                for sample_number, sample in enumerate(selected_data, start=1)
            ]
            for future in as_completed(futures):
                annotated, failed = future.result()
                changed += int(annotated)
                failures += int(failed)

    filtered_output_data = filter_selected_tasks(selected_data)
    write_json(args.output, filtered_output_data)

    print(
        f"annotated {changed} sample(s), failures={failures}, "
        f"selected_tasks={len(filtered_output_data)}, input={args.input}, output={args.output}"
    )
    if args.dry_run:
        print("dry-run: no LLM calls were made")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
