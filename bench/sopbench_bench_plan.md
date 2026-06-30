# context
1. use sop to test temporal constraint dynamics
2. user turn history will be a sop construction history, also with some tasks
3. only change from cctu: not different scope, but a temporal improvement in SOP
4. sample 200 tasks with distribution among 830 tasks, these 200 tasks will be used to test the temporal constraint dynamics


# pilot sizing (K=8, aligned with CCTU scale)

## source pool (SOPBench → step1)
- tasks: **200** / 830 (domain-proportional sample, `sample_task.py`)
- full SOP `•` per task: **~54** (all actions; `eval_step1_sop.json`)
- `user_goal` anchor `•` per task: **~4** (mean; **786** total across 200 tasks)
- other-action `•` available per task: **~50** (not all used)

## anchor selection (per task)
- keep **all** `user_goal` constraints: **G ≈ 4**
- sample from other actions: **K = 8**
- **total anchors ≈ 12** / task (**~2,400** across 200 tasks)
- sampling note: prefer constraints on the `user_goal` path (login / internal_check_*), plus a few unrelated actions as distractors

## temporal noise (per anchor)
- **0–3** temporal modifications / anchor (not scope noise); mean **~1.5**
- estimated constraint events / task: **(4+8) × 2.5 ≈ 30** (target: CCTU merged sequence **~29**)

## user turn history budget (vs CCTU)
| mode | turns / task | notes |
|------|-------------|--------|
| temporal only (intro + 0–3 mods / anchor) | **~25–35** | no carryover |
| CCTU-like (+ ~5 carryover per constraint event) | **~150–190** | CCTU reference: **~188** history + **1** eval |

CCTU reference (200 tasks): anchor **~4–5**, merged sequence **~29**, history **~188**.


# main pipeline
for each system prompt:
    extract all constraints
    return neat system prompt
    # done: `filter_sop.py` → `mac-sop_system_prompt.json` + `eval_step1_sop.json`

for every task, get task-level SOP:
    anchors = all user_goal `•` + sample K=8 from other actions
        for every anchor:
            add 0-3 (randomly sampled) temporal modifications
            # not scope noise (unlike CCTU global/project/phase)
        merge all constraints, verified by graph resolver
        
        for each anchor & temporal mod:
            populate user turns
            # tone: designing / revising the sop


## steps
filter_sop.py          ✅ done
select_anchors.py      ← anchors = G + K=8
temporal_noise.py      ← 0–3 mods / anchor
merge + validate       ← graph resolver
task_hist_gen.py       ← user turns
export_sop_data.py     ← 最终 data/
bridge + grade         ← 跑 benchmark

evaluation代码修改(for temporal_noise.py)
分析 / 质检（process→null 比例、semantics-only、假差异）
    ↓
batch：为 process=null 的 noisy 生成 eval 侧参数/配置（或改 bridge，不一定动 domain 源码）

## note: university graph-builder fix (2026-06-29)

`temporal_noise.py` action-level rulebase compiles full action dependency trees via SOPBench
`dfsgather_invfunccalldirgraph`. University `default_dep_full` expands `constraint_dependencies`
into `chain` nodes that expose bare `internal_check_*` singles; those must appear in
`constraint_processes` or compilation raises `KeyError`.

**Fix:** in `bench/SOPBench/env/domains/university/university_assistant.py`, register
`internal_check_username_exists` and `internal_check_course_exists` in `constraint_processes`
(same pattern as existing `internal_check_major_exists` / `internal_check_minor_exists`).
Without this, all university action units in step3 were skipped (`noise_generated=0`).