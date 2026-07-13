"""Audit CCTU tool JSON schemas against Python simulator signatures.

Finds mismatches like ``historical_event_retriever`` where the simulator requires
``date_range`` but the published schema marks it optional.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from bench.MAC.cctu.bridge import MAC_CCTU_DATA_DIR, REPO_ROOT, parse_cctu_codes

DEFAULT_INPUT_DATA = REPO_ROOT / "bench" / "CCTU" / "data" / "input_data.jsonl"
DEFAULT_MAC_TASKS = MAC_CCTU_DATA_DIR / "mac-cctu-tasks.json"

ISSUE_SEVERITY = {
    "sim_required_not_in_schema_required": "high",
    "schema_required_not_in_sim_signature": "high",
    "schema_prop_not_in_sim": "medium",
    "sim_param_not_in_schema_props": "low",
    "missing_schema": "high",
    "missing_simulator": "medium",
    "unparseable_simulator": "low",
}


@dataclass(slots=True)
class ParsedSimulator:
    params: list[tuple[str, bool]]  # (name, has_default)
    has_vararg: bool
    has_varkw: bool


@dataclass(slots=True)
class SchemaMismatch:
    task_id: str
    tool: str
    kind: str
    severity: str
    param: str | None = None
    schema_required: list[str] | None = None
    sim_required: list[str] | None = None
    schema_properties: list[str] | None = None
    sim_params: list[str] | None = None
    detail: str | None = None


def parse_simulator_signature(code: str) -> ParsedSimulator | None:
    """Parse the first ``def`` in simulator source code."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        args = node.args
        defaults_offset = len(args.args) - len(args.defaults)
        params: list[tuple[str, bool]] = []
        for index, arg in enumerate(args.args):
            params.append((arg.arg, index >= defaults_offset))
        for index, arg in enumerate(args.kwonlyargs):
            params.append((arg.arg, args.kw_defaults[index] is not None))
        return ParsedSimulator(
            params=params,
            has_vararg=args.vararg is not None,
            has_varkw=args.kwarg is not None,
        )
    return None


def tool_schema_from_entry(tool: dict[str, Any]) -> dict[str, Any]:
    if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
        fn = tool["function"]
        schema = fn.get("parameters")
    else:
        schema = tool.get("input_schema") or tool.get("parameters")
    if isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}, "required": []}


def tool_name_from_entry(tool: dict[str, Any]) -> str | None:
    if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
        name = tool["function"].get("name")
    else:
        name = tool.get("name")
    return str(name) if isinstance(name, str) and name else None


def schema_sets(schema: dict[str, Any]) -> tuple[set[str], set[str]]:
    properties = set((schema.get("properties") or {}).keys())
    required = set(schema.get("required") or [])
    return properties, required


def sim_sets(parsed: ParsedSimulator) -> tuple[set[str], set[str]]:
    all_params = {name for name, _ in parsed.params}
    required = {name for name, has_default in parsed.params if not has_default}
    return all_params, required


def audit_tool_pair(
    *,
    task_id: str,
    tool_name: str,
    schema: dict[str, Any] | None,
    code: str | None,
) -> list[SchemaMismatch]:
    issues: list[SchemaMismatch] = []

    if schema is None:
        if code:
            issues.append(
                SchemaMismatch(
                    task_id=task_id,
                    tool=tool_name,
                    kind="missing_schema",
                    severity=ISSUE_SEVERITY["missing_schema"],
                    detail="Simulator code exists but no JSON schema was published for this tool.",
                )
            )
        return issues

    if not code:
        issues.append(
            SchemaMismatch(
                task_id=task_id,
                tool=tool_name,
                kind="missing_simulator",
                severity=ISSUE_SEVERITY["missing_simulator"],
                detail="Tool schema exists but simulator code is missing.",
            )
        )
        return issues

    parsed = parse_simulator_signature(code)
    if parsed is None:
        issues.append(
            SchemaMismatch(
                task_id=task_id,
                tool=tool_name,
                kind="unparseable_simulator",
                severity=ISSUE_SEVERITY["unparseable_simulator"],
                detail="Could not parse simulator source with AST.",
            )
        )
        return issues

    schema_props, schema_required = schema_sets(schema)
    sim_all, sim_required = sim_sets(parsed)
    schema_required_sorted = sorted(schema_required)
    sim_required_sorted = sorted(sim_required)
    schema_props_sorted = sorted(schema_props)
    sim_all_sorted = sorted(sim_all)

    for param in sorted(sim_required - schema_required):
        issues.append(
            SchemaMismatch(
                task_id=task_id,
                tool=tool_name,
                kind="sim_required_not_in_schema_required",
                severity=ISSUE_SEVERITY["sim_required_not_in_schema_required"],
                param=param,
                schema_required=schema_required_sorted,
                sim_required=sim_required_sorted,
                detail=(
                    f"Simulator parameter '{param}' has no default but is absent from schema.required. "
                    "Agents following the schema may omit it and trigger runtime errors."
                ),
            )
        )

    for param in sorted(schema_required - sim_all):
        issues.append(
            SchemaMismatch(
                task_id=task_id,
                tool=tool_name,
                kind="schema_required_not_in_sim_signature",
                severity=ISSUE_SEVERITY["schema_required_not_in_sim_signature"],
                param=param,
                schema_required=schema_required_sorted,
                sim_params=sim_all_sorted,
                detail=(
                    f"Schema marks '{param}' as required but the simulator function does not accept it."
                ),
            )
        )

    if not parsed.has_varkw:
        for param in sorted(schema_props - sim_all):
            issues.append(
                SchemaMismatch(
                    task_id=task_id,
                    tool=tool_name,
                    kind="schema_prop_not_in_sim",
                    severity=ISSUE_SEVERITY["schema_prop_not_in_sim"],
                    param=param,
                    schema_properties=schema_props_sorted,
                    sim_params=sim_all_sorted,
                    detail=(
                        f"Schema exposes optional property '{param}' but the simulator rejects unknown kwargs."
                    ),
                )
            )

        for param in sorted(sim_all - schema_props):
            issues.append(
                SchemaMismatch(
                    task_id=task_id,
                    tool=tool_name,
                    kind="sim_param_not_in_schema_props",
                    severity=ISSUE_SEVERITY["sim_param_not_in_schema_props"],
                    param=param,
                    schema_properties=schema_props_sorted,
                    sim_params=sim_all_sorted,
                    detail=(
                        f"Simulator accepts '{param}' but it is missing from schema.properties."
                    ),
                )
            )

    return issues


def load_input_data_tasks(path: Path) -> Iterable[tuple[str, dict[str, str], dict[str, dict[str, Any]]]]:
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        task_id = str(row.get("id"))
        codes = parse_cctu_codes(row.get("codes"))
        tools_raw = row.get("tools")
        if isinstance(tools_raw, str):
            tools_raw = json.loads(tools_raw)
        schemas: dict[str, dict[str, Any]] = {}
        if isinstance(tools_raw, list):
            for tool in tools_raw:
                if not isinstance(tool, dict):
                    continue
                name = tool_name_from_entry(tool)
                if name:
                    schemas[name] = tool_schema_from_entry(tool)
        yield task_id, codes, schemas


def load_mac_tasks(path: Path, *, samples_by_id: dict[str, dict[str, Any]]) -> Iterable[tuple[str, dict[str, str], dict[str, dict[str, Any]]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    tasks = payload.get("tasks") if isinstance(payload, dict) else payload
    if not isinstance(tasks, list):
        raise ValueError(f"Unexpected MAC tasks payload in {path}")
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("cctu_id") or task.get("id"))
        sample = samples_by_id.get(task_id, {})
        codes = parse_cctu_codes(sample.get("codes") or task.get("codes"))
        schemas: dict[str, dict[str, Any]] = {}
        tools_raw = task.get("tools")
        if isinstance(tools_raw, list):
            for tool in tools_raw:
                if not isinstance(tool, dict):
                    continue
                name = tool_name_from_entry(tool)
                if name:
                    schemas[name] = tool_schema_from_entry(tool)
        yield task_id, codes, schemas


def load_samples_by_id(input_data_path: Path) -> dict[str, dict[str, Any]]:
    samples: dict[str, dict[str, Any]] = {}
    for line in input_data_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        samples[str(row.get("id"))] = row
    return samples


def audit_tasks(
    tasks: Iterable[tuple[str, dict[str, str], dict[str, dict[str, Any]]]],
    *,
    skip_tools: set[str] | None = None,
) -> list[SchemaMismatch]:
    skip = skip_tools or {"send_message"}
    issues: list[SchemaMismatch] = []
    for task_id, codes, schemas in tasks:
        tool_names = sorted(set(codes) | set(schemas))
        for tool_name in tool_names:
            if tool_name in skip:
                continue
            issues.extend(
                audit_tool_pair(
                    task_id=task_id,
                    tool_name=tool_name,
                    schema=schemas.get(tool_name),
                    code=codes.get(tool_name),
                )
            )
    return issues


def summarize_issues(issues: list[SchemaMismatch]) -> dict[str, Any]:
    by_kind = Counter(issue.kind for issue in issues)
    by_severity = Counter(issue.severity for issue in issues)
    by_tool = Counter(issue.tool for issue in issues)
    pattern_counts = Counter(
        (issue.kind, issue.tool, issue.param or "")
        for issue in issues
    )
    tasks_with_issues = sorted({issue.task_id for issue in issues})
    return {
        "issue_count": len(issues),
        "task_count_with_issues": len(tasks_with_issues),
        "task_ids_with_issues": tasks_with_issues,
        "by_kind": dict(by_kind),
        "by_severity": dict(by_severity),
        "by_tool": dict(by_tool.most_common(20)),
        "top_patterns": [
            {
                "kind": kind,
                "tool": tool,
                "param": param or None,
                "count": count,
                "severity": ISSUE_SEVERITY.get(kind, "unknown"),
            }
            for (kind, tool, param), count in pattern_counts.most_common(30)
        ],
    }


def build_report(
    *,
    source: str,
    source_path: str,
    issues: list[SchemaMismatch],
) -> dict[str, Any]:
    return {
        "schema_version": "CCTUToolSchemaAuditV1",
        "source": source,
        "source_path": source_path,
        "summary": summarize_issues(issues),
        "issues": [asdict(issue) for issue in issues],
    }


def print_human_summary(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"Source: {report['source']} ({report['source_path']})")
    print(f"Issues: {summary['issue_count']} across {summary['task_count_with_issues']} tasks")
    print("By severity:", summary["by_severity"])
    print("By kind:", summary["by_kind"])
    print("\nTop patterns:")
    for item in summary["top_patterns"][:15]:
        param = f".{item['param']}" if item["param"] else ""
        print(
            f"  [{item['severity']}] {item['count']:3d}x {item['kind']} :: "
            f"{item['tool']}{param}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit CCTU tool schema vs simulator mismatches.")
    parser.add_argument(
        "--source",
        choices=("input_data", "mac_tasks"),
        default="input_data",
        help="Task export to scan (default: bench/CCTU/data/input_data.jsonl).",
    )
    parser.add_argument(
        "--input-data",
        type=Path,
        default=DEFAULT_INPUT_DATA,
        help="Path to CCTU input_data.jsonl.",
    )
    parser.add_argument(
        "--mac-tasks",
        type=Path,
        default=DEFAULT_MAC_TASKS,
        help="Path to MAC mac-cctu-tasks.json (used with --source mac_tasks).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report output path.",
    )
    parser.add_argument(
        "--min-severity",
        choices=("low", "medium", "high"),
        default="low",
        help="Only include issues at or above this severity.",
    )
    return parser.parse_args()


SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


def filter_by_severity(issues: list[SchemaMismatch], min_severity: str) -> list[SchemaMismatch]:
    threshold = SEVERITY_RANK[min_severity]
    return [issue for issue in issues if SEVERITY_RANK.get(issue.severity, 0) >= threshold]


def main() -> None:
    args = parse_args()
    if args.source == "input_data":
        tasks = load_input_data_tasks(args.input_data)
        source_path = str(args.input_data)
    else:
        samples = load_samples_by_id(args.input_data)
        tasks = load_mac_tasks(args.mac_tasks, samples_by_id=samples)
        source_path = str(args.mac_tasks)

    issues = filter_by_severity(audit_tasks(tasks), args.min_severity)
    report = build_report(source=args.source, source_path=source_path, issues=issues)
    print_human_summary(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
