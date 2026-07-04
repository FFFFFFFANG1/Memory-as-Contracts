from __future__ import annotations

import random
from pathlib import Path

from bench.MAC.construct.sop.user_turn_population import (
    ActionRequestPool,
    collect_eval_field_slots,
    eligible_carryover_actions,
    generate_carryover_block_from_pool,
    normalize_carryover_dedupe_key,
    plan_carryover_count,
    seed_carryover_seen_keys,
    visible_tool_actions,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_action_request_pool_covers_all_sopbench_user_goals() -> None:
    pool = ActionRequestPool.from_sopbench_data(REPO_ROOT / "bench/SOPBench/data")
    summary = pool.summary()
    assert summary["action_count"] >= 50
    assert summary["template_count"] >= summary["action_count"]


def test_carryover_sampling_uses_multiple_visible_actions() -> None:
    step2 = __import__("json").loads(
        (REPO_ROOT / "bench/MAC/sopbench/mid_data/eval_step2_anchors.json").read_text(encoding="utf-8")
    )
    tasks = step2 if isinstance(step2, list) else step2["tasks"]
    bank_task = next(task for task in tasks if task["domain"] == "bank")

    pool = ActionRequestPool.from_sopbench_data(REPO_ROOT / "bench/SOPBench/data")
    visible = visible_tool_actions(bank_task)
    eligible = eligible_carryover_actions(
        domain="bank",
        visible_actions=visible,
        action_pool=pool,
    )
    assert len(eligible) >= 8

    eval_prompt = str(bank_task.get("mac_task_summary") or "")
    _, eval_grounding = collect_eval_field_slots(eval_prompt, bank_task)
    rng = random.Random(13)
    seen_keys = seed_carryover_seen_keys(eval_prompt=eval_prompt, output_turns=[])
    entries = generate_carryover_block_from_pool(
        domain="bank",
        visible_actions=visible,
        action_pool=pool,
        eval_prompt=eval_prompt,
        eval_grounding=eval_grounding,
        forbidden=set(),
        carryover_count=8,
        rng=rng,
        seen_keys=seen_keys,
    )
    assert len(entries) == 8
    actions = {entry["source_action"] for entry in entries}
    assert len(actions) >= 2
    for entry in entries:
        assert entry["content"]
        assert entry["source_action"] in eligible


def test_pool_templates_are_deduped_per_action() -> None:
    pool = ActionRequestPool.from_sopbench_data(REPO_ROOT / "bench/SOPBench/data")
    for (domain, action), templates in pool.templates.items():
        keys = [normalize_carryover_dedupe_key(template.prompt) for template in templates]
        assert len(keys) == len(set(keys)), f"duplicate templates for {domain}:{action}"


def test_carryover_dedupe_is_task_level_across_blocks() -> None:
    step2 = __import__("json").loads(
        (REPO_ROOT / "bench/MAC/sopbench/mid_data/eval_step2_anchors.json").read_text(encoding="utf-8")
    )
    tasks = step2 if isinstance(step2, list) else step2["tasks"]
    bank_task = next(task for task in tasks if task["domain"] == "bank")
    pool = ActionRequestPool.from_sopbench_data(REPO_ROOT / "bench/SOPBench/data")
    visible = visible_tool_actions(bank_task)
    eval_prompt = str(bank_task.get("mac_task_summary") or "")
    _, eval_grounding = collect_eval_field_slots(eval_prompt, bank_task)
    rng = random.Random(7)
    seen_keys = seed_carryover_seen_keys(eval_prompt=eval_prompt, output_turns=[])

    all_entries: list[dict[str, str]] = []
    for _ in range(4):
        block = generate_carryover_block_from_pool(
            domain="bank",
            visible_actions=visible,
            action_pool=pool,
            eval_prompt=eval_prompt,
            eval_grounding=eval_grounding,
            forbidden=set(),
            carryover_count=6,
            rng=rng,
            seen_keys=seen_keys,
        )
        all_entries.extend(block)

    content_keys = [normalize_carryover_dedupe_key(entry["content"]) for entry in all_entries]
    assert len(content_keys) == len(set(content_keys))
    assert len(all_entries) == 24


def test_plan_carryover_count_uses_truncated_normal_range() -> None:
    import random
    from argparse import Namespace

    args = Namespace(
        carryover_min=1,
        carryover_max=10,
        carryover_mean=5.5,
        carryover_std=2.0,
    )
    rng = random.Random(13)
    samples = [plan_carryover_count(rng, args) for _ in range(2000)]
    assert all(1 <= value <= 10 for value in samples)
    assert min(samples) == 1
    assert max(samples) == 10
    assert 4 <= sum(samples) / len(samples) <= 7
