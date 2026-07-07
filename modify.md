# MAC system modification notes

Date: 2026-07-07
Branch: `system`

This note summarizes the recent MAC system changes, the current half-modified
source state, and the latest live evaluation results. It is intentionally a
status record, not a claim that the current dirty tree is ready to merge.

## Recent Modification History

1. Synced the branch state around `main`, `bench_v2`, and `system`.
   - `system` was aligned with the newer active-hook-plan work from `main`.
   - The older `bench_v2` naming was retired in favor of `system`.
   - CCTU/SOPBench runtime data and construction scripts were repeatedly synced
     from the relevant branches as benchmark files changed.

2. Simplified MAC from soft preferences toward hard runtime constraints.
   - Removed the `no_validator` fallback path.
   - Removed soft-preference framing from the active MAC direction.
   - Reduced scope vocabulary toward `global`, `session`, `workspace`, and
     `path`.
   - Started treating benchmark project/phase alignment as path-oriented rather
     than as separate project/module abstractions.

3. Added active hook plan runtime concepts.
   - Introduced active pre/post hook plan filtering so tool calls do not need to
     scan every stored hook.
   - Kept `check_pattern` as the second-stage matcher inside the active hook
     lists.
   - Added path-aware action signatures and active-path propagation for
     MACBench-style tasks.

4. Shifted extraction toward IR-style policies.
   - Added PolicyIR extraction and runtime-oriented policy metadata.
   - Experimented with XACML-inspired policy/obligation/monitor structure, but
     kept runtime hooks API-free.
   - Moved from batch-only extraction toward per-user-turn extraction.

5. Added unified per-turn add/update/remove operations.
   - Each eligible user turn retrieves top-k candidate constraints using BM25.
   - A single LLM call returns `noop`, `add`, `remove`, `replace`, `refine`, or
     `exception` operations.
   - This was intended to unify CCTU add-style tasks and SOPBench update-style
     tasks without a separate update trigger path.
   - Current default top-k in the live run was `5`.

6. Updated benchmark-facing grading behavior.
   - MAC-rejected tool calls are filtered out of CCTU/SOPBench trajectory
     grading, so a blocked wrong call should not penalize the final order if the
     agent retries correctly.
   - MAC reject tool results now return a corrective message of the form:
     `[memory] This tool call is not allowed due to "..."; please retry after revise.`
   - CCTU grading gained a fallback when local legacy `input_data.jsonl` /
     `unsolved_set` is unavailable: it uses task-local messages, answer,
     constraints, and tools. This fallback is useful for local MAC scoring but
     is not identical to official CCTU ACC.
   - SOPBench grading now tolerates missing `step2/step4` construction
     intermediates and falls back to available manifest/runtime data.

## Current Dirty Source State

The current working tree contains unfinished modifications across:

- `src/memory_as_contracts/*`
  - IR extraction, matching, resolver, hook runtime, hook plan, retrieval, and
    rule evaluation are in-progress.
- `bench/MAC/agent/*`
  - MAC memory provider now supports unified per-turn ops, active paths, reject
    messages, progress logging, and rejected-call filtering.
- `bench/MAC/cctu/*` and `bench/construct/cctu/*`
  - CCTU bridge/grader fallback and noise-eval metric output changes.
- `bench/MAC/sopbench/*`, `bench/MAC/construct/sop/*`, and
  `bench/construct/sop/*`
  - SOPBench runtime data, construction/grading scripts, and fallback grading.
- Tests under `tests/`
  - Active hook plan and IR-related test coverage are partially updated.

There are also many untracked duplicate files with names ending in ` 2.py` or
similar. These were not included in this documentation commit.

## Latest Live Evaluation

All runs used the current IR-style MAC path with unified per-turn extraction,
BM25 candidate retrieval, top-k `5`, and no live validator generation.

### CCTU, first 5 tasks

Run output:
`/tmp/mac_cctu5_unified_ops_agent_20260707.json`

Grade output:
`/tmp/mac_cctu5_unified_ops_grade_20260707.json`

Scores:

- `answer pass`: `0.20`
- `constraint pass`: `0.00`
- `joint pass`: `0.00`
- `constraint violation rate`: `0.529`
- all 5 tasks reached `send_message` before `max_iterations`

Runtime counts:

- extraction LLM calls: `111`
- validator LLM calls: `0`
- MAC rejects: `51`
- unified ops total: `140`
- unified adds: `98`
- unified noops: `28`
- unified refines: `10`
- unified replaces: `3`
- unified removes: `1`
- JSON parse errors: `7`

Important caveat:

- Local CCTU legacy `unsolved_set/input_data.jsonl` is missing, so this local
  grading uses the fallback described above. The answer/constraint pass values
  are still informative for MAC behavior, but the legacy ACC comparison is not
  fully official.

### SOPBench, first 5 tasks

Run output:
`/tmp/mac_sop5_unified_ops_agent_20260707.json`

Grade output:
`/tmp/mac_sop5_unified_ops_grade_20260707.json`

Scores:

- `answer pass`: `0.80`
- `constraint pass`: `0.00`
- `joint pass`: `0.00`
- `constraint violation rate`: `0.60`
- native task success: `3/5`
- 4 tasks reached `send_message`; 1 task reached `max_iterations`

Runtime counts:

- extraction LLM calls: `167`
- validator LLM calls: `0`
- MAC rejects: `16`
- unified ops total: `190`
- unified adds: `41`
- unified exceptions: `4`
- unified refines: `13`
- unified removes: `20`
- unified replaces: `12`
- unified noops: `100`
- JSON parse errors: `2`

## Interpretation

The current `constraint pass = 0` is not mainly because evaluation is absent.
Both CCTU and SOPBench produced unit-level constraint-follow signals. The direct
reason is that every task missed at least one active/anchor process constraint,
and task-level `constraint pass` is all-or-nothing.

However, the zero is amplified by several issues:

1. Real MAC/agent failures:
   - Some CCTU response-format and tool-count constraints were violated.
   - Some SOPBench anchor actions were missed or not replayed in strict order.

2. MAC over-blocking:
   - SOPBench showed cases where `authenticate_admin_password` was repeatedly
     rejected even after the agent attempted prerequisite checks.
   - This suggests the current monitor representation still does not reliably
     distinguish "the check was called" from "the check returned a satisfying
     state".

3. Evaluation/data rough edges:
   - SOPBench has dependency evaluator errors such as missing `amount` or
     `credit_balance` fields.
   - SOPBench can treat internal graph actions such as `internal_get_database`
     as active misses, which may require adapter/benchmark alignment.
   - CCTU local scoring is using fallback data because the legacy sample file is
     not present locally.

## Current Design Assessment

The useful general pieces so far:

- per-turn extraction with retrieved candidate constraints;
- unified operation format for add/update/delete-like edits;
- active hook plan filtering before `check_pattern` matching;
- action-log based monitor state;
- rejected-call filtering in graders;
- no validator-generation LLM at runtime.

The parts that remain weak:

- monitor predicates are still too shallow for stateful constraints that depend
  on tool outputs;
- relation resolution is currently LLM-heavy at extraction time rather than
  structurally proven;
- some generated policies overgeneralize benchmark procedural statements into
  runtime constraints;
- SOPBench adapter alignment is not clean enough for all graph/internal actions;
- all-or-nothing `constraint pass` hides partial progress.

## Next Steps

1. Fix SOPBench grading/adapter alignment first.
   - Decide whether internal graph actions such as `internal_get_database`
     should be agent-observable anchors.
   - Fix dependency evaluator missing-field failures.

2. Improve monitor state.
   - Represent tool output predicates explicitly, not just prior action
     existence.
   - Allow obligations like "prior tool call returned field/value satisfying
     predicate".

3. Reduce over-blocking.
   - Audit MAC rejects, especially repeated rejects after prerequisite checks.
   - Ensure reject feedback points the agent to the exact missing action or
     missing satisfied state.

4. Re-run the same 5+5 live evaluation after adapter and monitor fixes.

