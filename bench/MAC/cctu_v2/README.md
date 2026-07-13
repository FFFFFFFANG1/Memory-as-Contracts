# CCTU v2 Pilot

CCTU v2 evaluates memory-governed execution through controlled injection.
Canonical directive events and trace prefixes determine gold labels; rendered
dialogue never determines benchmark semantics.

## Build

```bash
PYTHONPATH=. uv run python -m bench.MAC.cctu_v2.constraint_audit
PYTHONPATH=. uv run python -m bench.MAC.cctu_v2.builder
PYTHONPATH=. uv run python -m bench.MAC.cctu_v2.run_baselines
```

Artifacts:

- `data/constraint_audit.json`: all 914 constraints, including conservative
  human-review flags.
- `data/crossed_gold_examples.json`: ten frozen, hand-selected blueprints.
- `data/pilot_40.json`: balanced 40-task structural pilot.
- `data/pilot_40_report.json`: validation and expansion decision.
- `data/baseline_probe_report.json`: oracle, long-context, and BM25
  information-sufficiency upper bounds. This symbolic probe is not an LLM
  agent score.
- `data/llm_baseline_corrected_summary.json`: corrected GLM-5.2 pilot result.
  The initial full runs are retained with `pre_lower_bound_fix` in their names,
  and the corrected lower-bound episode is stored separately for auditability.

## Important boundary

The automatic audit is not human gold.  Behavior-order/parallelism constraints
remain excluded from automatic pilot construction until reviewers confirm they
are optional user directives rather than intrinsic task dependencies.
