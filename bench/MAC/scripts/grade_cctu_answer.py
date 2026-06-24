"""Grade MAC memory-eval outputs with CCTU's post-run checks."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench.MAC.cctu.bridge import (
    MAC_CCTU_DATA_DIR,
    cctu_id_from_task_uid,
    cctu_samples_by_id,
    cctu_validators_dir,
    import_cctu_attr,
    load_cctu_eval_tasks,
)
from bench.MAC.scripts.run_paths import bench_grade_path, make_run_unique_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answers_file", type=Path, help="JSON output from run_memory_eval.py.")
    parser.add_argument("--bench", choices=["cctu"], default="cctu")
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard", "all"])
    parser.add_argument("--memory-system")
    parser.add_argument("--run-id")
    parser.add_argument("--cctu-data-dir", type=Path, default=MAC_CCTU_DATA_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--detail", action="store_true")
    return parser.parse_args()


def read_memory_output(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")
    header = payload.get("header")
    records = payload.get("records")
    if isinstance(header, dict) and isinstance(records, list):
        return header, [row for row in records if isinstance(row, dict)]
    raise ValueError(f"{path} is not a MACMemoryOutputV1 file")


def infer_bench(args: argparse.Namespace, header: dict[str, Any]) -> str:
    if args.bench:
        return args.bench
    value = header.get("bench")
    if isinstance(value, str) and value:
        return value
    return "cctu"


def infer_difficulty(args: argparse.Namespace, header: dict[str, Any]) -> str | None:
    if args.difficulty:
        return args.difficulty
    value = header.get("difficulty")
    if isinstance(value, str) and value in {"easy", "normal", "hard", "all"}:
        return value
    return None


def infer_memory_system(args: argparse.Namespace, header: dict[str, Any]) -> str:
    if args.memory_system:
        return args.memory_system
    value = header.get("memory_system")
    if isinstance(value, str) and value:
        return value
    raise ValueError("Could not infer memory system; pass --memory-system explicitly.")


def task_index(args: argparse.Namespace, header: dict[str, Any]) -> dict[str, dict[str, Any]]:
    bench = infer_bench(args, header)
    if bench == "cctu":
        tasks, _summary = load_cctu_eval_tasks(data_dir=args.cctu_data_dir)
        return {str(task.get("task_uid")): task for task in tasks if isinstance(task, dict)}
    raise ValueError(f"Unsupported bench for CCTU grading: {bench}")


def openai_tool_call(call: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(call.get("id") or ""),
        "type": "function",
        "function": {
            "name": str(call.get("name") or ""),
            "arguments": json.dumps(call.get("arguments") or {}, ensure_ascii=False),
        },
    }


def cctu_messages_from_events(row: dict[str, Any], sample: dict[str, Any]) -> list[dict[str, Any]]:
    messages = copy.deepcopy(sample.get("messages") or [])
    events = row.get("events")
    if not isinstance(events, list):
        final = row.get("final_answer")
        if isinstance(final, str):
            messages.append({"role": "assistant", "content": final})
        return messages

    appended_final = False
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event") == "model_response":
            raw_calls = event.get("tool_calls")
            calls = [call for call in raw_calls if isinstance(call, dict)] if isinstance(raw_calls, list) else []
            send_calls = [call for call in calls if call.get("name") == "send_message"]
            domain_calls = [call for call in calls if call.get("name") != "send_message"]
            content = event.get("content") if isinstance(event.get("content"), str) else ""
            if domain_calls:
                assistant: dict[str, Any] = {"role": "assistant", "content": content}
                assistant["tool_calls"] = [openai_tool_call(call) for call in domain_calls]
                messages.append(assistant)
            if send_calls:
                response = send_calls[-1].get("arguments", {}).get("response")
                messages.append({"role": "assistant", "content": response if isinstance(response, str) else ""})
                appended_final = True
            elif not domain_calls and content:
                messages.append({"role": "assistant", "content": content})
                appended_final = True
            continue

        if event.get("event") == "tool_result":
            if event.get("name") == "send_message":
                continue
            call_id = event.get("tool_call_id")
            content = event.get("result")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": str(call_id or ""), "content": content})

    if not appended_final:
        final = row.get("final_answer")
        if isinstance(final, str):
            messages.append({"role": "assistant", "content": final})
    return messages


def handler_constraint_indices(checker: Any) -> list[int]:
    """Map each checker handler back to its index in constraints_list."""
    registry = import_cctu_attr("utils.constraint_checker.handlers", "HANDLER_REGISTRY")
    indices: list[int] = []
    for idx, constraint in enumerate(checker.constraints):
        primary = str(constraint[0]).lower()
        secondary = str(constraint[1]).lower()
        if registry.get((primary, secondary)) is None:
            continue
        indices.append(idx)
    return indices


def replay_constraint_analysis(
    messages: list[dict[str, Any]],
    sample: dict[str, Any],
) -> tuple[list[dict[str, Any]], set[int], int]:
    """Replay assistant turns and return violations plus violated constraint indices."""
    checker_cls = import_cctu_attr("utils.constraint_checker", "DialogueConstraintChecker")
    turn_context_cls = import_cctu_attr("utils.constraint_checker.handlers.base", "TurnContext")
    strip_think = import_cctu_attr("utils.constraint_checker.check_utils", "_strip_think_keep_text")
    checker = checker_cls(sample=sample, max_turns=20, validators_dir=str(cctu_validators_dir()))
    constraint_total = len(checker.constraints)
    constraint_index_by_handler = handler_constraint_indices(checker)
    violated_indices: set[int] = set()
    violations: list[dict[str, Any]] = []

    for index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        tool_calls = [
            call
            for call in (message.get("tool_calls") or [])
            if call.get("function", {}).get("name") != "send_message"
        ]
        is_final = not tool_calls
        content = strip_think(message.get("content") or "")
        checker.update_round()
        ctx = turn_context_cls(
            is_final=is_final,
            content=content,
            tool_calls=tool_calls or [],
        )

        feedback_cls = import_cctu_attr("utils.constraint_checker.feedback", "Feedback")
        feedback = feedback_cls()
        for handler_index, handler in enumerate(checker.handlers):
            user_before = len(feedback.user_msgs)
            tool_before = sum(len(values) for values in feedback.tool_msgs_by_callid.values())
            handler.check(checker, ctx, feedback)
            tool_after = sum(len(values) for values in feedback.tool_msgs_by_callid.values())
            if len(feedback.user_msgs) > user_before or tool_after > tool_before:
                violated_indices.add(constraint_index_by_handler[handler_index])

        if_feedback = (
            [{"role": "user", "content": "\n".join(feedback.user_msgs).strip()}]
            if is_final and feedback.user_msgs
            else [
                {
                    "role": "tool",
                    "tool_call_id": str(call.get("id") or ""),
                    "content": "\n".join(feedback.tool_msgs_by_callid.get(str(call.get("id") or ""), [])).strip(),
                }
                for call in tool_calls
                if feedback.tool_msgs_by_callid.get(str(call.get("id") or ""))
            ]
        )
        if not is_final and tool_calls:
            feedbacks = checker.get_feedback_tool_arguments(if_feedback=if_feedback, tool_calls=tool_calls)
        else:
            feedbacks = if_feedback

        for feedback in feedbacks:
            content = feedback.get("content") if isinstance(feedback, dict) else ""
            if content:
                violations.append(
                    {
                        "message_index": index,
                        "role": feedback.get("role"),
                        "tool_call_id": feedback.get("tool_call_id"),
                        "content": content,
                    }
                )

    return violations, violated_indices, constraint_total


def replay_constraint_violations(messages: list[dict[str, Any]], sample: dict[str, Any]) -> list[dict[str, Any]]:
    violations, _violated_indices, _constraint_total = replay_constraint_analysis(messages, sample)
    return violations


def constraint_summaries(sample: dict[str, Any], violated_indices: set[int]) -> list[dict[str, Any]]:
    raw = sample.get("constraints_list") or []
    summaries: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, list) or len(item) < 3:
            continue
        summaries.append(
            {
                "index": index,
                "primary": str(item[0]),
                "secondary": str(item[1]),
                "desc": str(item[2]),
                "satisfied": index not in violated_indices,
            }
        )
    return summaries


def compute_ssr(*, constraint_total: int, violated_indices: set[int]) -> float:
    if constraint_total <= 0:
        return 1.0
    satisfied = constraint_total - len(violated_indices)
    return max(0.0, min(1.0, satisfied / constraint_total))


def grade_one(row: dict[str, Any], task: dict[str, Any] | None, samples: dict[str, dict[str, Any]]) -> dict[str, Any]:
    task_uid = str(row.get("task_uid") or "")
    cctu_id = str((task or {}).get("cctu_id") or cctu_id_from_task_uid(task_uid))
    sample = copy.deepcopy((task or {}).get("cctu_sample") or samples.get(cctu_id))
    if not isinstance(sample, dict):
        return {"task_uid": task_uid, "cctu_id": cctu_id, "SR": False, "PSR": False, "error": "missing_cctu_sample"}

    messages = cctu_messages_from_events(row, sample)
    solve_rate_is_one = import_cctu_attr("evaluation", "solve_rate_is_one")
    unsolved_set = json.loads(sample.get("unsolved_set"))
    acc = bool(solve_rate_is_one(messages, unsolved_set))
    violations, violated_indices, constraint_total = replay_constraint_analysis(messages, sample)
    ssr = compute_ssr(constraint_total=constraint_total, violated_indices=violated_indices)
    constraint_satisfied = constraint_total - len(violated_indices)
    final_index = max((idx for idx, msg in enumerate(messages) if msg.get("role") == "assistant"), default=-1)
    final_violations = [item for item in violations if item.get("message_index") == final_index]
    sr = bool(acc and not final_violations)
    psr = bool(acc and not violations)
    return {
        "task_uid": task_uid,
        "cctu_id": cctu_id,
        "SR": sr,
        "PSR": psr,
        "SSR": ssr,
        "acc": acc,
        "constraint_total": constraint_total,
        "constraint_satisfied": constraint_satisfied,
        "violated_constraint_indices": sorted(violated_indices),
        "constraints": constraint_summaries(sample, violated_indices),
        "violation_count": len(violations),
        "final_violation_count": len(final_violations),
        "stop_reason": row.get("stop_reason"),
        "violations": violations[:20],
    }


def aggregate(details: list[dict[str, Any]], tasks_by_uid: dict[str, dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {"Overall": details}
    for detail in details:
        task = tasks_by_uid.get(str(detail.get("task_uid"))) or {}
        source = str(task.get("data_source") or task.get("cctu_data_source") or "Unknown")
        groups.setdefault(source, []).append(detail)

    scores: dict[str, Any] = {}
    for name, rows in groups.items():
        if not rows:
            continue
        sr = sum(1 for row in rows if row.get("SR")) / len(rows) * 100
        psr = sum(1 for row in rows if row.get("PSR")) / len(rows) * 100
        acc = sum(1 for row in rows if row.get("acc")) / len(rows) * 100
        ssr = sum(float(row.get("SSR") or 0.0) for row in rows) / len(rows) * 100
        scores[name] = {
            "SR": f"{sr:.2f}",
            "PSR": f"{psr:.2f}",
            "SSR": f"{ssr:.2f}",
            "ACC": f"{acc:.2f}",
            "count": len(rows),
        }
    return scores


def output_path(
    args: argparse.Namespace,
    *,
    header: dict[str, Any],
    bench: str,
    memory_system: str,
) -> Path:
    if args.output:
        return args.output
    run_id = args.run_id or header.get("run_id") or make_run_unique_index()
    if args.output_dir:
        return args.output_dir / f"{memory_system}_{bench}_{run_id}.json"
    return bench_grade_path(memory_system, bench, str(run_id))


def main() -> None:
    args = parse_args()
    header, records = read_memory_output(args.answers_file)
    bench = infer_bench(args, header)
    difficulty = infer_difficulty(args, header)
    memory_system = infer_memory_system(args, header)
    tasks_by_uid = task_index(args, header)
    samples = cctu_samples_by_id()
    details = [
        grade_one(row, tasks_by_uid.get(str(row.get("task_uid") or "")), samples)
        for row in records
        if row.get("record_type") == "task_result"
    ]
    task_errors = sum(1 for row in records if row.get("record_type") == "task_error")
    payload = {
        "schema_version": "MACCCTUGradeV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_answers": str(args.answers_file),
        "bench": bench,
        "difficulty": difficulty,
        "memory_system": memory_system,
        "task_error_count": task_errors,
        "graded_task_count": len(details),
        "scores": aggregate(details, tasks_by_uid),
        "details": details if args.detail else [],
    }
    target = output_path(args, header=header, bench=bench, memory_system=memory_system)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target}")
    print(json.dumps(payload["scores"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
