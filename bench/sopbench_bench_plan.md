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
