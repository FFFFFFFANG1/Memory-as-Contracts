#!/usr/bin/env python3
"""Audit every exported CCTU constraint for CCTU-v2 suitability."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path("bench/MAC/cctu/data/mac-cctu-tasks.json")
DEFAULT_OUTPUT = Path("bench/MAC/cctu_v2/data/constraint_audit.json")


def _trajectory_type(primary: str, secondary: str, text: str) -> str:
    key = f"{primary} {secondary} {text}".lower()
    if primary == "Response":
        return "action_local"
    if "parallel" in key:
        return "parallelism"
    if "sequential" in key or " before " in key or " after " in key:
        return "order_based"
    if "specific tool" in key or "per tool" in key:
        return "tool_count_based"
    if "tool call count" in key or "total number of tool" in key:
        return "count_based"
    if "round" in key:
        return "round_count_based"
    return "trajectory_conditioned"


def _nature(primary: str, secondary: str) -> tuple[str, float, bool]:
    if primary == "Response":
        return "standing_user_directive", 0.90, False
    if primary == "Resource":
        return "standing_user_directive", 0.78, False
    if primary == "Behavior" and secondary == "Parallel Calls Count":
        return "standing_user_directive", 0.65, True
    if primary == "Behavior":
        return "unclear_intrinsic_dependency_risk", 0.45, True
    return "unclear", 0.30, True


def _descriptor_mismatch(primary: str, secondary: str, desc: str) -> bool:
    text = desc.lower()
    if primary == "Resource":
        return not any(token in text for token in ("call", "round", "turn", "invoke", "interaction"))
    if primary == "Response":
        return not any(
            token in text
            for token in ("response", "answer", "json", "markdown", "punctuation", "word", "character")
        )
    return False


def audit_constraint(task: dict[str, Any], constraint: dict[str, Any]) -> dict[str, Any]:
    primary = str(constraint.get("cctu_primary") or "")
    secondary = str(constraint.get("cctu_secondary") or "")
    raw = str(constraint.get("cctu_raw_desc") or "")
    desc = str(constraint.get("desc") or raw)
    nature, confidence, review = _nature(primary, secondary)
    dependency = _trajectory_type(primary, secondary, raw)
    action_local = dependency == "action_local"
    intrinsic_risk = nature == "unclear_intrinsic_dependency_risk"
    return {
        "task_uid": task["mac_task_uid"],
        "constraint_uid": constraint["mac_constraint_uid"],
        "task_summary": task.get("mac_task_summary"),
        "primary": primary,
        "secondary": secondary,
        "raw_text": raw,
        "normalized_text": desc,
        "directive_nature": nature,
        "dependency_type": dependency,
        "taxonomy_cells_supported": [
            "static_action_local" if action_local else "static_trajectory_conditioned",
            "dynamic_action_local" if action_local else "dynamic_trajectory_conditioned",
        ],
        "counterfactual_solvable": None if intrinsic_risk else True,
        "user_plausible": True if not intrinsic_risk else None,
        "supports_lifecycle": ["introduce", "amend", "revoke", "scope", "exception"],
        "descriptor_mismatch": _descriptor_mismatch(primary, secondary, desc),
        "review_required": review or _descriptor_mismatch(primary, secondary, desc),
        "auto_confidence": confidence,
        "audit_status": "auto_audited_pending_human" if review else "auto_audited",
        "exclusion_reason": "possible intrinsic task dependency" if intrinsic_risk else None,
    }


def build_audit(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [
        audit_constraint(task, constraint)
        for task in payload.get("tasks") or []
        for constraint in task.get("constraints") or []
    ]
    nature = Counter(row["directive_nature"] for row in rows)
    dependency = Counter(row["dependency_type"] for row in rows)
    primary = Counter(row["primary"] for row in rows)
    return {
        "schema_version": "CCTUV2ConstraintAuditV1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "deterministic conservative pre-audit; review_required rows are not human gold",
        "summary": {
            "constraint_count": len(rows),
            "task_count": len({row["task_uid"] for row in rows}),
            "review_required_count": sum(bool(row["review_required"]) for row in rows),
            "descriptor_mismatch_count": sum(bool(row["descriptor_mismatch"]) for row in rows),
            "by_primary": dict(sorted(primary.items())),
            "by_directive_nature": dict(sorted(nature.items())),
            "by_dependency_type": dict(sorted(dependency.items())),
        },
        "constraints": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    output = build_audit(payload)
    if output["summary"]["constraint_count"] != 914:
        raise SystemExit(f"expected 914 constraints, got {output['summary']['constraint_count']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
