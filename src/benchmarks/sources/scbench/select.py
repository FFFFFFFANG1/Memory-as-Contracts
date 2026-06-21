from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from benchmarks.sources.scbench.models import ScbenchCheckpoint, ScbenchTaskCandidate


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"SCBench config must be a mapping: {path}")
    return payload


def _checkpoint_order(config: dict[str, Any], checkpoint_id: str) -> int:
    checkpoint_cfg = (config.get("checkpoints") or {}).get(checkpoint_id) or {}
    order = checkpoint_cfg.get("order")
    if isinstance(order, int):
        return order
    try:
        return int(checkpoint_id.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return 999


def _test_files(problem_root: Path, checkpoint_id: str) -> list[Path]:
    tests_dir = problem_root / "tests"
    candidates = sorted(tests_dir.glob(f"test_{checkpoint_id}.py"))
    if candidates:
        return candidates
    return sorted(tests_dir.glob(f"*{checkpoint_id}*.py"))


def discover_scbench_tasks(problems_root: Path) -> list[ScbenchTaskCandidate]:
    tasks: list[ScbenchTaskCandidate] = []
    for config_path in sorted(problems_root.glob("*/config.yaml")):
        root = config_path.parent
        config = _load_config(config_path)
        checkpoints: list[ScbenchCheckpoint] = []
        checkpoint_cfg = config.get("checkpoints") or {}
        for checkpoint_id in sorted(checkpoint_cfg, key=lambda item: _checkpoint_order(config, item)):
            spec_path = root / f"{checkpoint_id}.md"
            if not spec_path.exists():
                continue
            checkpoints.append(
                ScbenchCheckpoint(
                    checkpoint_id=checkpoint_id,
                    order=_checkpoint_order(config, checkpoint_id),
                    spec_path=spec_path,
                    spec_text=strip_scbench_canary(spec_path.read_text(encoding="utf-8")),
                    test_files=_test_files(root, checkpoint_id),
                )
            )
        if not checkpoints:
            continue
        test_count = sum(len(checkpoint.test_files) for checkpoint in checkpoints)
        selection_score = len(checkpoints) * 100 + test_count
        tasks.append(
            ScbenchTaskCandidate(
                problem_id=str(config.get("name") or root.name),
                root=root,
                description=str(config.get("description") or ""),
                difficulty=config.get("difficulty"),
                category=config.get("category"),
                entry_file=config.get("entry_file"),
                tags=list(config.get("tags") or []),
                checkpoints=checkpoints,
                selection_score=selection_score,
            )
        )
    return tasks


def select_scbench_tasks(
    problems_root: Path,
    *,
    limit: int,
    min_checkpoints: int = 4,
    difficulties: set[str] | None = None,
) -> list[ScbenchTaskCandidate]:
    candidates = discover_scbench_tasks(problems_root)
    filtered = [
        task
        for task in candidates
        if len(task.checkpoints) >= min_checkpoints
        and (difficulties is None or (task.difficulty or "") in difficulties)
    ]
    filtered.sort(key=lambda task: (-task.selection_score, task.problem_id))
    return filtered[:limit]


def strip_scbench_canary(text: str) -> str:
    lines = []
    skipping_html_comment = False
    for line in text.splitlines():
        lower = line.lower()
        if "<!-- benchmark data should never appear" in lower:
            skipping_html_comment = True
            continue
        if skipping_html_comment:
            if "-->" in line:
                skipping_html_comment = False
            continue
        if "benchmark data should never appear" in lower:
            continue
        if "sentinel phrase:" in lower or "slop-code-bench-canary" in lower:
            continue
        lines.append(line)
    return "\n".join(lines).strip()
