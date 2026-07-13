from __future__ import annotations

import json
from pathlib import Path

from bench.MAC.cctu_v2.builder import build_gold, build_pilot, structural_report
from bench.MAC.cctu_v2.constraint_audit import build_audit
from bench.MAC.cctu_v2.core import candidate_allowed, resolve_active_directives, validate_episode
from bench.MAC.cctu_v2.run_baselines import run_probe


ROOT = Path(__file__).resolve().parents[1]


def source_tasks() -> dict:
    return json.loads((ROOT / "bench/MAC/cctu/data/mac-cctu-tasks.json").read_text())


def test_audit_covers_all_914_constraints() -> None:
    audit = build_audit(source_tasks())
    assert audit["summary"]["constraint_count"] == 914
    assert audit["summary"]["task_count"] == 200
    assert sum(audit["summary"]["by_primary"].values()) == 914


def test_lifecycle_resolution_and_trace_jointly_flip_action() -> None:
    context = {"project": "p"}
    old = {
        "text": "at most three calls",
        "scope": {"project": "p"},
        "predicate": {"kind": "max_tool_calls", "limit": 3, "tool": None},
    }
    new = {
        "text": "at most two calls",
        "scope": {"project": "p"},
        "predicate": {"kind": "max_tool_calls", "limit": 2, "tool": None},
    }
    before = [{"event_index": 0, "event_type": "introduce", "directive_id": "d", "version": 1, "directive": old}]
    after = [*before, {"event_index": 1, "event_type": "amend", "directive_id": "d", "version": 2, "directive": new}]
    prefix = [{"kind": "tool_call", "tool": "x"}, {"kind": "tool_call", "tool": "x"}]
    candidate = {"kind": "tool_call", "tool": "x"}
    assert candidate_allowed(resolve_active_directives(before, context), prefix, candidate)
    assert not candidate_allowed(resolve_active_directives(after, context), prefix, candidate)


def test_gold_and_pilot_are_balanced_and_valid() -> None:
    audit = build_audit(source_tasks())
    gold = build_gold(audit)
    pilot = build_pilot(audit)
    assert len(gold) == 10
    assert len(pilot) == 40
    assert all(not validate_episode(episode) for episode in [*gold, *pilot])
    report = structural_report(pilot)
    assert report["condition_count"] == 160
    assert report["counterfactual_flip_rate"] == 1.0
    assert report["oracle_accuracy"] == 1.0
    assert set(report["taxonomy_distribution"].values()) == {10}


def test_baseline_probe_runs_requested_memory_systems() -> None:
    audit = build_audit(source_tasks())
    payload = {"episodes": build_pilot(audit)[:4]}
    report = run_probe(payload)
    assert set(report["summaries"]) == {
        "oracle",
        "long_context",
        "bm25@1",
        "bm25@3",
        "bm25@10",
    }
    assert report["summaries"]["oracle"]["accuracy"] == 1.0
    assert report["summaries"]["long_context"]["accuracy"] == 1.0
