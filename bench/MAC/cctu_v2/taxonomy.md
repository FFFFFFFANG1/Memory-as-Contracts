# CCTU v2 Taxonomy (Frozen for Pilot V1)

## Research object

CCTU v2 evaluates **memory-governed execution**.  The current task is natively
solvable without memory; memory supplies user-authored standing directives that
govern how the task may be executed.

At checkpoint `t`:

```text
active_directives_t = Resolve(directive_events_<=t, current_context_t)
valid(action_t) = AND verifier(directive, trace_<t, action_t)
```

## 2 x 2 primary taxonomy

| Lifecycle | Action-local | Trajectory-conditioned |
| --- | --- | --- |
| Static | Current directive constrains the proposed action alone. | Current directive depends on prior calls/order/count. |
| Dynamic | Introduce/amend/revoke/scope changes which local directive applies. | Lifecycle state and trajectory prefix jointly determine validity. |

Canonical cell identifiers:

- `static_action_local`
- `dynamic_action_local`
- `static_trajectory_conditioned`
- `dynamic_trajectory_conditioned`

## Pilot lifecycle operations

- `introduce`
- `amend`
- `revoke`
- `scope` (represented by context matching rather than destructive deletion)
- `override` / `consume_exception`

Physical deletion is out of scope.  Revoked and superseded directives remain in
the event log so obsolete-rule misapplication can be measured.

## In scope

- Explicit user-authored `MUST`, `MUST_NOT`, and bounded operational directives.
- Project/phase/task/resource applicability.
- Response requirements, action budgets, tool-specific budgets, and optional
  ordering/parallelism requirements with executable checks.
- Active-rule misses and obsolete/out-of-scope over-application.

## Out of scope for the pilot

- Latent preference induction.
- Environment-intrinsic tool dependencies.
- Physical privacy deletion/right-to-be-forgotten.
- Subjective style appropriateness that requires an unvalidated LLM judge.
- Claims about real-time latency; the pilot is incremental/online, not a latency benchmark.

## Difficulty controls

- Lifecycle depth: number of state-changing events.
- Scope depth: global/project/phase/task/resource.
- Competing directive count.
- Trace-prefix length.
- Predicate state: unused, boundary, exhausted, exception-consumed.
