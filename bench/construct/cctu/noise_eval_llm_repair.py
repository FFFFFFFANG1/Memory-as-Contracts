#!/usr/bin/env python3
"""LLM repair pass for MAC-CCTU noise evaluators that still fail verification.

Reads the latest verification audit for each artifact, sends the constraint,
current code, and audit flags to an LLM, validates mechanically, re-audits,
and writes repaired artifacts.  Runs in parallel with ThreadPoolExecutor.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.construct.cctu.noise_eval_generation import (  # noqa: E402
    SYSTEM_PROMPT,
    call_llm,
    load_env,
    normalize_package,
    parse_llm_json,
    resolve_llm_config,
    resolve_path,
    sha256_text,
    stable_json,
    tool_like_names_from_text,
    tool_names_for_task,
    verify_package,
)
from bench.construct.cctu.noise_eval_repair import (  # noqa: E402
    build_python_from_structured,
)
from bench.construct.cctu.noise_eval_verify import (  # noqa: E402
    VerifyJob,
    code_path_for_artifact,
    iter_artifact_paths,
    verify_one,
    write_json,
)

DEFAULT_ARTIFACT_DIR = Path("bench/MAC/cctu/data/noise_check_code")
DEFAULT_TASKS = Path("bench/MAC/cctu/data/mac-cctu-tasks.json")
DEFAULT_ENV_FILE = Path("bench/.env")
DEFAULT_MANUAL_QUEUE = Path("bench/cctu/mid_data/eval_step5_10_noise_eval_manual_queue.json")
DEFAULT_CACHE = Path("bench/cctu/mid_data/noise_eval_llm_repair_cache.json")
DEFAULT_OUTPUT = Path("bench/cctu/mid_data/eval_step5_11_noise_eval_llm_repair.json")
DEFAULT_VERIFY_OUTPUT = Path("bench/cctu/mid_data/eval_step5_5_noise_eval_verify_post_llm.json")

FLAG_GUIDE: dict[str, str] = {
    "coverage_missing:tool_count": "Check tool call counts via trace['tool_calls'] when the constraint requires it.",
    "coverage_missing:tool_usage": "Verify required/forbidden tools were invoked using trace['tool_calls'].",
    "coverage_missing:interaction_rounds": "Check len(trace['trajectory']) against interaction turn limits.",
    "coverage_missing:markdown": "Check Markdown markers in trace['final_response'] when required.",
    "coverage_missing:json": "Validate JSON in trace['final_response'] when required.",
    "coverage_missing:length": "Check word/character counts in trace['final_response'] when required.",
    "coverage_missing:date": "Check date formatting in trace['final_response'] when required.",
    "coverage_missing:punctuation": "Check ending punctuation in trace['final_response'] when required.",
    "counterfactual_no_tool_calls_should_fail_passed": (
        "Return observed_followed=false when the constraint requires tool usage but tool_calls is empty."
    ),
    "counterfactual_markdown_plain_should_fail_passed": (
        "Return observed_followed=false for plain text when Markdown is required."
    ),
    "counterfactual_short_response_should_fail_passed": (
        "Return observed_followed=false when the response is too short for a stated length minimum."
    ),
    "counterfactual_forbidden_tool_should_fail_passed": (
        "Return observed_followed=false when a forbidden tool appears in tool_calls."
    ),
    "possible_composite_constraint_partially_covered": (
        "The constraint has multiple requirements; cover each one mentioned in the constraint text."
    ),
    "possible_tool_logic_without_tool_constraint": (
        "Do not read tool_calls unless the constraint actually requires tool behavior."
    ),
    "possible_json_checker_contains_length_logic": (
        "Do not mix unrelated length checks into a JSON-only constraint."
    ),
}


@dataclass(frozen=True)
class RepairJob:
    artifact_path: Path
    verify_item: dict[str, Any]


def repo_relative(path: Path) -> str:
    try:
        return str(resolve_path(path).relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> Any:
    return json.loads(resolve_path(path).read_text(encoding="utf-8"))


def load_cache(path: Path) -> dict[str, Any]:
    target = resolve_path(path)
    if not target.exists():
        return {"schema_version": "MACCCTUNoiseEvalLLMRepairCacheV1", "items": {}}
    payload = load_json(target)
    if not isinstance(payload, dict):
        return {"schema_version": "MACCCTUNoiseEvalLLMRepairCacheV1", "items": {}}
    payload.setdefault("items", {})
    return payload


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    write_json(path, cache)


def build_llm_repair_prompt(
    *,
    constraint: str,
    type_hint: list[str],
    tool_names: list[str],
    verify_item: dict[str, Any],
    current_code: str | None,
    previous_errors: list[str] | None = None,
) -> str:
    flags = [str(item) for item in verify_item.get("flags") or []]
    flag_help = {flag: FLAG_GUIDE.get(flag, FLAG_GUIDE.get(flag.split(":")[0], "")) for flag in flags}
    counterfactual = verify_item.get("counterfactual_results") or []
    compact_cf = [
        {
            "case": item.get("case"),
            "expected_observed": item.get("expected_observed"),
            "observed_followed": item.get("observed_followed"),
            "reason": item.get("reason"),
        }
        for item in counterfactual
        if isinstance(item, dict)
    ][:8]

    payload: dict[str, Any] = {
        "constraint": constraint,
        "weak_type_hint": " / ".join(type_hint) if type_hint else None,
        "available_tool_names": tool_names[:30],
        "verification_audit": {
            "severity": verify_item.get("severity"),
            "flags": flags,
            "missing_features": verify_item.get("missing_features") or [],
            "verify_errors": verify_item.get("verify_errors") or [],
            "flag_guide": {key: value for key, value in flag_help.items() if value},
            "counterfactual_mismatches": compact_cf,
        },
        "current_evaluator_code": (current_code or "")[:7000] or None,
        "instruction": (
            "Rewrite the evaluator so it faithfully checks ONLY this constraint and resolves every "
            "verification_audit issue above. Prefer structured specs for counts, tool usage, length, "
            "and simple response-format checks; use Python only when necessary. "
            "Do not reward-hack: empty or irrelevant checks are unacceptable."
        ),
    }
    if previous_errors:
        payload["previous_attempt_errors"] = previous_errors
        payload["repair_instruction"] = "Fix the listed mechanical or audit errors. Return corrected compact JSON only."
    return json.dumps(payload, indent=2, ensure_ascii=False)


def structured_to_python_package(
    package: dict[str, Any],
    *,
    constraint: str,
    type_hint: list[str],
) -> dict[str, Any] | None:
    code = build_python_from_structured(
        package,
        constraint_text=constraint,
        type_hint=type_hint,
    )
    if not code:
        return None
    converted = {
        "status": "success",
        "evaluator_type": "python",
        "family": package.get("family"),
        "spec": package.get("spec"),
        "check_code": code,
        "notes": [*(package.get("notes") or []), "converted from structured LLM package"],
    }
    if verify_package(converted):
        return None
    return converted


def apply_package(
    artifact_path: Path,
    package: dict[str, Any],
    *,
    backup_root: Path | None,
    artifact_root: Path,
) -> None:
    artifact = load_json(artifact_path)
    if not isinstance(artifact, dict):
        raise ValueError("artifact is not a JSON object")

    code_path = code_path_for_artifact(artifact_path)
    if backup_root is not None:
        rel = artifact_path.relative_to(artifact_root)
        for source in (artifact_path, code_path):
            if not source.exists():
                continue
            target = backup_root / rel if source == artifact_path else backup_root / rel.with_suffix(".py")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    evaluator = {
        key: value
        for key, value in package.items()
        if key not in {"check_code"}
    }
    generation = dict(evaluator.get("generation") or {})
    generation.update(
        {
            "method": "llm",
            "repair": "llm_verify_repair",
            "repaired_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    evaluator["generation"] = generation
    artifact["evaluator"] = evaluator
    artifact_path.write_text(json.dumps(artifact, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")

    if package.get("evaluator_type") == "python" and isinstance(package.get("check_code"), str):
        code_path.write_text(str(package["check_code"]).rstrip() + "\n", encoding="utf-8")
    elif code_path.exists():
        code_path.unlink()


def repair_one(job: RepairJob, args: argparse.Namespace, cache: dict[str, Any], tasks_by_uid: dict[str, dict[str, Any]]) -> dict[str, Any]:
    artifact_path = resolve_path(job.artifact_path)
    artifact = load_json(artifact_path)
    if not isinstance(artifact, dict):
        return {"status": "skipped", "reason": "invalid artifact", "artifact_path": repo_relative(artifact_path)}

    node_id = str(artifact.get("node_id") or "")
    constraint = str(artifact.get("constraint_text") or "")
    type_hint = [str(item) for item in artifact.get("type_hint") or []]
    task_uid = str(artifact.get("task_uid") or "")
    task = tasks_by_uid.get(task_uid, {})
    tool_names = sorted(set(tool_names_for_task(task) + tool_like_names_from_text(constraint)))

    code_path = code_path_for_artifact(artifact_path)
    current_code = code_path.read_text(encoding="utf-8") if code_path.exists() else None

    cache_key = sha256_text(
        stable_json(
            {
                "node_id": node_id,
                "constraint_sha256": sha256_text(constraint),
                "flags": job.verify_item.get("flags"),
                "model": args.model,
                "prompt_version": 1,
            }
        )
    )
    cache_lock = args._cache_lock
    with cache_lock:
        cached = cache["items"].get(cache_key)

    def apply_cached_package(cached_entry: dict[str, Any]) -> dict[str, Any]:
        package = normalize_package(dict(cached_entry["package"]))
        if package.get("evaluator_type") == "structured":
            converted = structured_to_python_package(package, constraint=constraint, type_hint=type_hint)
            if converted is not None:
                package = converted
        apply_package(
            artifact_path,
            package,
            backup_root=args._backup_root,
            artifact_root=args._artifact_root,
        )
        post = verify_one(VerifyJob(0, artifact_path))
        return {
            "status": "repaired_cache",
            "node_id": node_id,
            "severity_before": job.verify_item.get("severity"),
            "severity_after": post.get("severity"),
            "flags_after": post.get("flags"),
            "artifact_path": repo_relative(artifact_path),
        }

    if args.from_cache:
        if isinstance(cached, dict) and isinstance(cached.get("package"), dict):
            try:
                return apply_cached_package(cached)
            except Exception as exc:  # noqa: BLE001
                return {
                    "status": "failed",
                    "node_id": node_id,
                    "severity_before": job.verify_item.get("severity"),
                    "severity_after": job.verify_item.get("severity"),
                    "errors": [f"cache_apply_error: {type(exc).__name__}: {exc}"],
                    "artifact_path": repo_relative(artifact_path),
                }
        return {
            "status": "failed",
            "node_id": node_id,
            "severity_before": job.verify_item.get("severity"),
            "severity_after": job.verify_item.get("severity"),
            "errors": ["cache_miss"],
            "artifact_path": repo_relative(artifact_path),
        }

    if isinstance(cached, dict) and cached.get("status") == "success" and not args.retry_cache:
        try:
            return apply_cached_package(cached)
        except Exception:  # noqa: BLE001
            pass

    errors: list[str] = []
    last_package: dict[str, Any] | None = None
    for attempt in range(1, max(1, args.repair_attempts) + 1):
        prompt = build_llm_repair_prompt(
            constraint=constraint,
            type_hint=type_hint,
            tool_names=tool_names,
            verify_item=job.verify_item,
            current_code=current_code,
            previous_errors=errors or None,
        )
        try:
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
            package = normalize_package(parse_llm_json(raw))
            last_package = package
        except Exception as exc:  # noqa: BLE001
            errors = [f"llm_error: {type(exc).__name__}: {exc}"]
            continue

        mech_errors = verify_package(package)
        if mech_errors:
            errors = mech_errors
            continue

        if package.get("evaluator_type") == "structured":
            converted = structured_to_python_package(package, constraint=constraint, type_hint=type_hint)
            if converted is not None:
                package = converted

        try:
            apply_package(
                artifact_path,
                package,
                backup_root=args._backup_root,
                artifact_root=args._artifact_root,
            )
        except Exception as exc:  # noqa: BLE001
            errors = [f"apply_error: {type(exc).__name__}: {exc}"]
            continue

        post = verify_one(VerifyJob(0, artifact_path))
        if post.get("severity") == "pass":
            with cache_lock:
                cache["items"][cache_key] = {"status": "success", "package": package, "attempts": attempt}
            return {
                "status": "repaired",
                "node_id": node_id,
                "attempts": attempt,
                "severity_before": job.verify_item.get("severity"),
                "severity_after": post.get("severity"),
                "flags_before": job.verify_item.get("flags"),
                "artifact_path": repo_relative(artifact_path),
            }

        audit_errors = [f"audit:{flag}" for flag in post.get("flags") or []]
        verify_errors = [str(item) for item in post.get("verify_errors") or []]
        errors = audit_errors + verify_errors
        current_code = code_path.read_text(encoding="utf-8") if code_path.exists() else current_code

    with cache_lock:
        cache["items"][cache_key] = {
            "status": "failed",
            "errors": errors,
            "package": last_package,
        }
    post = verify_one(VerifyJob(0, artifact_path))
    return {
        "status": "failed",
        "node_id": node_id,
        "severity_before": job.verify_item.get("severity"),
        "severity_after": post.get("severity"),
        "flags_after": post.get("flags"),
        "errors": errors[:12],
        "artifact_path": repo_relative(artifact_path),
    }


def collect_jobs(args: argparse.Namespace) -> list[RepairJob]:
    if args.input_queue is not None:
        payload = load_json(args.input_queue)
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("input queue must contain an items list")
        jobs: list[RepairJob] = []
        paths: list[Path] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("artifact_path") or "")
            if rel:
                paths.append(resolve_path(Path(rel)))
        if args.limit is not None:
            paths = paths[: max(0, args.limit)]

        def _verify_path(index_path: tuple[int, Path]) -> RepairJob:
            index, path = index_path
            return RepairJob(artifact_path=path, verify_item=verify_one(VerifyJob(index, path)))

        workers = min(args.max_workers, max(1, len(paths)))
        if workers == 1:
            jobs = [_verify_path((index, path)) for index, path in enumerate(paths, start=1)]
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                jobs = list(executor.map(_verify_path, list(enumerate(paths, start=1))))
        return jobs

    allowed = set(args.severity)
    paths = iter_artifact_paths(args.artifact_dir)
    if args.limit is not None:
        paths = paths[: max(0, args.limit)]

    def _verify_path(index_path: tuple[int, Path]) -> RepairJob | None:
        index, path = index_path
        item = verify_one(VerifyJob(index, path))
        if item.get("severity") not in allowed:
            return None
        return RepairJob(artifact_path=path, verify_item=item)

    print(f"collecting flagged jobs from {len(paths)} artifacts...", flush=True)
    workers = min(args.max_workers, 8)
    jobs: list[RepairJob] = []
    if workers == 1:
        for index, path in enumerate(paths, start=1):
            job = _verify_path((index, path))
            if job is not None:
                jobs.append(job)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for job in executor.map(_verify_path, list(enumerate(paths, start=1))):
                if job is not None:
                    jobs.append(job)
    return jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument("--input-queue", type=Path, help="Optional manual queue JSON; default re-verifies all artifacts.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verify-output", type=Path, default=DEFAULT_VERIFY_OUTPUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument(
        "--severity",
        action="append",
        default=["needs_human", "coverage_review", "review"],
        help="Severities to repair when re-verifying.",
    )
    parser.add_argument("--repair-attempts", type=int, default=3)
    parser.add_argument("--retry-cache", action="store_true")
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Skip LLM calls; apply packages already stored in the cache file.",
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--api-key")
    parser.add_argument("--max-tokens", type=int, default=2400)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument(
        "--jobs-report",
        type=Path,
        help="Reuse artifact paths from a prior LLM repair report (skips full re-verify scan).",
    )
    parser.add_argument("--dry-run", action="store_true", help="List jobs only; do not call the LLM.")
    return parser.parse_args()


def jobs_from_report(report_path: Path, *, max_workers: int) -> list[RepairJob]:
    report = load_json(report_path)
    results = report.get("results") if isinstance(report, dict) else []
    if not isinstance(results, list):
        raise ValueError("jobs report must contain a results list")
    paths = [resolve_path(Path(str(item.get("artifact_path") or ""))) for item in results if isinstance(item, dict)]
    paths = [path for path in paths if path.exists()]

    def _verify_path(index_path: tuple[int, Path]) -> RepairJob:
        index, path = index_path
        return RepairJob(artifact_path=path, verify_item=verify_one(VerifyJob(index, path)))

    workers = min(max_workers, max(1, len(paths)))
    if workers == 1:
        return [_verify_path((index, path)) for index, path in enumerate(paths, start=1)]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_verify_path, list(enumerate(paths, start=1))))


def main() -> int:
    args = parse_args()
    args.max_workers = min(8, max(1, args.max_workers))
    args._cache_lock = threading.Lock()
    args._llm_calls_used = 0

    if args.env_file:
        load_env(args.env_file)
    else:
        load_env(DEFAULT_ENV_FILE if (REPO_ROOT / "bench/.env").exists() else None)

    if not args.dry_run:
        resolve_llm_config(args)

    tasks_payload = load_json(args.tasks)
    tasks = tasks_payload.get("tasks") if isinstance(tasks_payload, dict) else []
    tasks_by_uid = {
        str(task.get("mac_task_uid") or task.get("task_uid") or ""): task
        for task in tasks
        if isinstance(task, dict)
    }

    jobs = (
        jobs_from_report(args.jobs_report, max_workers=args.max_workers)
        if args.jobs_report is not None
        else collect_jobs(args)
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = resolve_path(args.artifact_dir)
    args._artifact_root = artifact_root
    args._backup_root = resolve_path(
        args.backup_dir or (artifact_root.parent / f"noise_check_code_backup/llm_{timestamp}")
    )

    print(f"llm repair jobs: {len(jobs)} max_workers={args.max_workers}", flush=True)
    if args.dry_run:
        for job in jobs[:20]:
            print(f"- {job.verify_item.get('node_id')} {job.verify_item.get('severity')} {job.verify_item.get('flags', [])[:3]}")
        return 0

    cache = load_cache(args.cache)
    results: list[dict[str, Any]] = []
    started = time.time()

    if args.max_workers == 1:
        for job in jobs:
            results.append(repair_one(job, args, cache, tasks_by_uid))
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            futures = {executor.submit(repair_one, job, args, cache, tasks_by_uid): job for job in jobs}
            for index, future in enumerate(as_completed(futures), start=1):
                results.append(future.result())
                if index % 25 == 0 or index == len(jobs):
                    passed = sum(1 for item in results if item.get("severity_after") == "pass")
                    print(f"progress {index}/{len(jobs)} pass_so_far={passed}", flush=True)

    save_cache(args.cache, cache)

    repaired = [item for item in results if item.get("status") in {"repaired", "repaired_cache"}]
    failed = [item for item in results if item.get("status") == "failed"]
    skipped = [item for item in results if item.get("status") == "skipped"]
    pass_after = sum(1 for item in results if item.get("severity_after") == "pass")

    report = {
        "schema_version": "MACCCTUNoiseEvalLLMRepairReportV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "job_count": len(jobs),
        "repaired_count": len(repaired),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
        "pass_after_count": pass_after,
        "elapsed_seconds": round(time.time() - started, 2),
        "backup_dir": repo_relative(args._backup_root),
        "results": results,
    }
    write_json(args.output, report)

    print(
        "llm repair complete: "
        f"jobs={len(jobs)} repaired={len(repaired)} failed={len(failed)} "
        f"pass_after={pass_after} backup={repo_relative(args._backup_root)} "
        f"output={repo_relative(args.output)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
