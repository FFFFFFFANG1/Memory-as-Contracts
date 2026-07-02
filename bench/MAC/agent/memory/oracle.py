"""Oracle memory baseline: inject eval-time active constraints into `<memory>`."""

from __future__ import annotations

from typing import Any

from bench.MAC.agent.memory.base import MemoryRequest, MemoryResult

ORACLE_MEMORY_PREAMBLE = (
    "Oracle constraints active for the current evaluation task. "
    "Follow these constraints exactly."
)

SOP_DECISION_INTRO = (
    "Overall success condition:\n"
    "Every Section must pass.\n"
    "Within an alternative-path Section, satisfying ANY ONE Path is enough."
)

SOP_REQUIRED_SECTION_TITLE = "Required checks"
SOP_ALTERNATIVE_SECTION_TITLE = "Alternative eligibility paths"


def _bench_family(task: dict[str, Any]) -> str:
    task_uid = str(task.get("task_uid") or "")
    if task.get("cctu_id") or task_uid.startswith("mac-cctu"):
        return "cctu"
    if task.get("user_goal") or task_uid.startswith("sopbench:"):
        return "sopbench"
    return "unknown"


def _constraint_type_label(constraint: dict[str, Any]) -> str:
    primary = constraint.get("cctu_primary")
    secondary = constraint.get("cctu_secondary")
    if isinstance(primary, str) and primary.strip():
        if isinstance(secondary, str) and secondary.strip() and secondary != primary:
            return f"{primary}/{secondary}"
        return primary.strip()
    raw_type = constraint.get("type")
    if isinstance(raw_type, list):
        parts = [str(item).strip() for item in raw_type if str(item).strip()]
        if parts:
            return "/".join(parts)
    if isinstance(raw_type, str) and raw_type.strip():
        return raw_type.strip()
    return "Constraint"


def _constraint_description(constraint: dict[str, Any]) -> str:
    for key in ("cctu_raw_desc", "desc", "text"):
        value = constraint.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _render_cctu_constraints(task: dict[str, Any]) -> tuple[list[str], str]:
    lines: list[str] = []
    constraints = task.get("constraints")
    if isinstance(constraints, list) and constraints:
        for index, constraint in enumerate(constraints, start=1):
            if not isinstance(constraint, dict):
                continue
            description = _constraint_description(constraint)
            if not description:
                continue
            label = _constraint_type_label(constraint)
            lines.append(f"{index}. [{label}] {description}")
        if lines:
            return lines, "task.constraints"

    fallback_lines: list[str] = []
    constraints_list = task.get("constraints_list")
    if isinstance(constraints_list, list):
        for index, item in enumerate(constraints_list, start=1):
            if isinstance(item, list) and len(item) >= 3:
                primary = str(item[0]).strip()
                secondary = str(item[1]).strip()
                description = str(item[2]).strip()
                label = f"{primary}/{secondary}" if secondary and secondary != primary else primary
                fallback_lines.append(f"{index}. [{label}] {description}")
            elif isinstance(item, str) and item.strip():
                fallback_lines.append(f"{index}. {item.strip()}")
    return fallback_lines, "task.constraints_list"


def _verbalize_sop_single(
    *,
    domain: str,
    constraint_id: str,
    params: dict[str, Any],
    dep_params: dict[str, Any],
) -> str:
    try:
        from bench.MAC.construct.sop.noise_eval import verbalize_single  # noqa: WPS433

        return verbalize_single(domain, constraint_id, params, dep_params).strip()
    except Exception:  # noqa: BLE001
        return constraint_id.strip()


def _sop_dependency_kind(dep: Any) -> str:
    if isinstance(dep, list) and dep and isinstance(dep[0], str):
        return dep[0]
    return ""


def _format_sop_single_line(
    dep: Any,
    *,
    domain: str,
    dep_params: dict[str, Any],
) -> str:
    constraint_id = str(dep[1])
    params = dep[2] if len(dep) >= 3 and isinstance(dep[2], dict) else {}
    return _verbalize_sop_single(
        domain=domain,
        constraint_id=constraint_id,
        params=params,
        dep_params=dep_params,
    )


def _collect_required_checks(
    dep: Any,
    *,
    domain: str,
    dep_params: dict[str, Any],
) -> tuple[list[str], list[Any]]:
    kind = _sop_dependency_kind(dep)
    if kind == "single" and len(dep) >= 2:
        return [_format_sop_single_line(dep, domain=domain, dep_params=dep_params)], []
    if kind in {"or", "gate"}:
        return [], [dep]
    if kind in {"and", "chain"} and len(dep) >= 2 and isinstance(dep[1], list):
        checks: list[str] = []
        alternatives: list[Any] = []
        for child in dep[1]:
            child_checks, child_alternatives = _collect_required_checks(
                child,
                domain=domain,
                dep_params=dep_params,
            )
            checks.extend(child_checks)
            alternatives.extend(child_alternatives)
        return checks, alternatives
    return [], []


def _format_path_checks(
    dep: Any,
    *,
    domain: str,
    dep_params: dict[str, Any],
    indent: int = 0,
) -> list[str]:
    prefix = "  " * indent
    kind = _sop_dependency_kind(dep)
    if kind == "single" and len(dep) >= 2:
        return [f"{prefix}- {_format_sop_single_line(dep, domain=domain, dep_params=dep_params)}"]
    if kind in {"and", "chain"} and len(dep) >= 2 and isinstance(dep[1], list):
        lines: list[str] = []
        for child in dep[1]:
            lines.extend(
                _format_path_checks(
                    child,
                    domain=domain,
                    dep_params=dep_params,
                    indent=indent,
                )
            )
        return lines
    if kind in {"or", "gate"} and len(dep) >= 2 and isinstance(dep[1], list):
        lines = [f"{prefix}- Satisfy ANY ONE option below:"]
        for index, child in enumerate(dep[1], start=1):
            lines.append(f"{prefix}  Option {index}:")
            lines.extend(
                _format_path_checks(
                    child,
                    domain=domain,
                    dep_params=dep_params,
                    indent=indent + 2,
                )
            )
        return lines
    return []


def _format_sop_decision_checklist(
    dependency: Any,
    *,
    domain: str,
    dep_params: dict[str, Any],
) -> list[str]:
    required_checks, alternative_nodes = _collect_required_checks(
        dependency,
        domain=domain,
        dep_params=dep_params,
    )
    sections: list[tuple[str, list[str]]] = []

    if required_checks:
        lines = ["All checks below must pass:"]
        lines.extend(f"- {check}" for check in required_checks)
        sections.append((SOP_REQUIRED_SECTION_TITLE, lines))

    for node in alternative_nodes:
        kind = _sop_dependency_kind(node)
        children = node[1] if len(node) >= 2 and isinstance(node[1], list) else []
        lines = [
            "At least one Path below must pass. Do not reject just because one Path fails."
        ]
        for index, child in enumerate(children, start=1):
            path_name = chr(ord("A") + index - 1) if index <= 26 else str(index)
            lines.append("")
            lines.append(f"Path {path_name}:")
            path_lines = _format_path_checks(
                child,
                domain=domain,
                dep_params=dep_params,
            )
            lines.extend(path_lines or ["- No additional checks."])
        if kind in {"or", "gate"}:
            sections.append((SOP_ALTERNATIVE_SECTION_TITLE, lines))

    if not sections:
        return []

    lines = [SOP_DECISION_INTRO]
    if len(sections) == 1:
        lines.extend(["", "Overall rule:", "Section 1 MUST pass."])
    else:
        lines.extend(["", "Overall rule:"])
        for index in range(1, len(sections) + 1):
            conjunction = "AND " if index > 1 else ""
            lines.append(f"{conjunction}Section {index} MUST pass.")

    for index, (title, section_lines) in enumerate(sections, start=1):
        lines.append("")
        lines.append(f"Section {index}: {title}")
        lines.extend(section_lines)

    execution_parts: list[str] = []
    for index, (title, _) in enumerate(sections, start=1):
        if title == SOP_ALTERNATIVE_SECTION_TITLE:
            execution_parts.append(f"at least one Path in Section {index} passes")
        else:
            execution_parts.append(f"Section {index} passes")
    lines.append("")
    lines.append("Execution rule:")
    lines.append(f"Call the user-goal tool iff {' AND '.join(execution_parts)}.")
    return lines


def _render_sop_constraints_from_tree(task: dict[str, Any]) -> tuple[list[str], str]:
    user_goal = str(task.get("user_goal") or "").strip()
    domain = str(task.get("domain") or "").strip()
    patched = task.get("patched_sopbench_task")
    if not isinstance(patched, dict) or not domain:
        return [], "none"

    dependency = patched.get("constraints")
    dep_params = patched.get("constraint_parameters")
    if not isinstance(dep_params, dict):
        dep_params = {}
    if not dependency:
        return [], "none"

    checklist_lines = _format_sop_decision_checklist(
        dependency,
        domain=domain,
        dep_params=dep_params,
    )
    if not checklist_lines:
        return [], "none"

    lines = [f"Goal: `{user_goal}`"]
    lines.extend(checklist_lines)
    return lines, "patched_sopbench_task.constraints[checklist]"


def _render_sop_constraints_flat(task: dict[str, Any]) -> tuple[list[str], str]:
    user_goal = str(task.get("user_goal") or "").strip()
    constraints = task.get("constraints")
    lines: list[str] = []
    if isinstance(constraints, list):
        matched = [
            constraint
            for constraint in constraints
            if isinstance(constraint, dict)
            and (not user_goal or str(constraint.get("action") or "") == user_goal)
        ]
        for index, constraint in enumerate(matched, start=1):
            description = _constraint_description(constraint)
            if not description:
                continue
            action = str(constraint.get("action") or user_goal or "user_goal")
            lines.append(f"{index}. [{action}] {description}")
        if lines:
            return lines, "task.constraints[user_goal]"

    patched = task.get("patched_sopbench_task")
    if isinstance(patched, dict):
        dependency = patched.get("constraints")
        if dependency:
            lines.append(f"1. [{user_goal or 'user_goal'}] {json_safe_dependency(dependency)}")
            return lines, "patched_sopbench_task.constraints"
    return [], "none"


def _render_sop_constraints(task: dict[str, Any]) -> tuple[list[str], str]:
    structured_lines, structured_source = _render_sop_constraints_from_tree(task)
    if structured_lines:
        return structured_lines, structured_source
    return _render_sop_constraints_flat(task)


def json_safe_dependency(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class OracleMemoryProvider:
    """Performance-ceiling memory mode with eval-time oracle constraints."""

    name = "oracle"

    def build_memory(self, request: MemoryRequest) -> MemoryResult:
        task = request.task if isinstance(request.task, dict) else {}
        bench_family = _bench_family(task)

        if bench_family == "cctu":
            constraint_lines, oracle_source = _render_cctu_constraints(task)
        elif bench_family == "sopbench":
            constraint_lines, oracle_source = _render_sop_constraints(task)
        else:
            constraint_lines, oracle_source = [], "unsupported_bench"

        if constraint_lines:
            memory = ORACLE_MEMORY_PREAMBLE + "\n\n" + "\n".join(constraint_lines)
        else:
            memory = ORACLE_MEMORY_PREAMBLE

        metadata = {
            "past_turn_count": len(request.past_user_turns),
            "included_turn_count": 0,
            "oracle_source": oracle_source,
            "constraint_count": len(constraint_lines),
            "bench_family": bench_family,
        }
        if bench_family == "sopbench":
            metadata["user_goal"] = task.get("user_goal")
        if bench_family == "cctu":
            metadata["cctu_id"] = task.get("cctu_id")

        return MemoryResult(
            system_name=self.name,
            memory=memory,
            metadata=metadata,
        )
