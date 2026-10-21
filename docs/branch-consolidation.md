# Mainline consolidation and PolicyIR-only runtime

Prepared on 2026-10-21 from bench_v2 `e7e7536f` and main `a28ba4ad`.
The owner selected `main` as the mainline, retired generated Python validators,
and kept unified-ops extraction off.

## Consolidated contents

- Carry bench_v2's MAC PolicyIR implementation, CCTU v2 pilot, tool-schema and
  runtime repairs, and materialized benchmark data onto main.
- Preserve main's Mem0 DeepSeek configuration, consolidated CCTU noise tooling
  paths, SOP tests, benchmark metrics and documentation.
- Keep CCTU `noise_follow_rate` and diagnostic counts. Fix the pre-existing
  diagnostics crash by computing comparison outcomes explicitly.
- Make SOP carryover/delta tests consume checked-in runtime data instead of
  ignored construction `mid_data`. Historical July scores are labeled as such;
  this change does not generate new experimental numbers.
- `system` is an ancestor of bench_v2; it has no additional committed changes.

## Runtime decisions implemented

- PolicyIR is the only executable MAC rule evaluator. Delete the generated
  validator generator, verifier/installer, sandbox/runtime, dispatcher, and
  legacy runtime-scope helper; remove their public runtime exports and CLI
  commands. Remove `--mac-live-validator` and its provider configuration.
- Switch both generic adapter entry points to `PolicyIRContractExtractor`.
  Ordinary extraction followed by ConflictResolver remains the default;
  retiring Python validators does not enable unified ops.
- Unified ops defaults to false and no longer silently enables itself from
  `MAC_UNIFIED_OPS_EXTRACTION`. An explicit experiment CLI flag can still opt in.
- Keep historical validator database records/types for non-destructive storage
  compatibility. They are never queried for execution. An applicable hard rule
  without PolicyIR returns ASK with a migration/re-extraction message. Historical
  `validator_verdicts` receipt field naming remains for output compatibility.
- Keep CCTU and SOPBench benchmark scoring evaluators. They measure the agent's
  task/constraint performance and are independent of MAC runtime validators.

The dedicated generated-validator tests are retired with their component.
Active-hook and adapter ingestion coverage is migrated to PolicyIR, with new
regressions for legacy-code non-execution, removed imports/commands, and defaults.

## Validation

The final targeted runtime/consolidation/SOP selection passed 84 tests. This
includes PolicyIR execution, active hooks, CLI, history scope, adapter default
selection, Mem0 configuration, and migrated SOP tests.

Full-suite results and the untouched bench_v2 comparison are saved under
`artifacts/branch-consolidation/` in the main workspace. This repository already
contains tests requiring absent CCTU `input_data.jsonl` and tests expecting
obsolete schema/scope/compiler behavior; a full-suite pass is not claimed.
No live model experiment or real Mem0 provider request was performed.

Final main-workspace suite: **260 passed, 51 failed, 2 deselected** (Python
3.12.14). The comparable untouched bench_v2 suite, excluding the two retired
generated-validator test files, had **232 passed, 52 failed, 2 deselected**.
Every final failure also occurs in that baseline; no new failing test ID was
introduced. The obsolete SOP clarification test was replaced with current-API
coverage. Failure identities and raw reports are retained in the artifacts.


## Git state

The integration is applied to the original repository's `main` working tree.
The session can edit source files but cannot write that repository's `.git`.
Publication therefore uses an isolated temporary clone containing the same
source tree, with both main and bench_v2 preserved in its ancestry. The original
checkout's local refs and index require subsequent synchronization. No old
remote branch is deleted. No further product decision is required for this change.
