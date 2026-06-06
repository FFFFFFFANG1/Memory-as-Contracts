# Memory-as-Contracts

Memory-as-Contracts is a contract layer for memory-mediated agent behavior.

## Language

**Stage 2**:
The implementation stage that adds MAC v4's event-sourced validator runtime to the existing pattern-gate system.
_Avoid_: state_2, version4

**MAC v4**:
The capability version where contracts may be enforced by validators over an observable action log and persistent rule-local state.
_Avoid_: state_2

**Action Log**:
The append-only record of committed tool actions observed after execution, including the assistant tool call, tool result, timestamp, raw arguments, raw output, and optional reasoning metadata.
_Avoid_: conversation log, proposed-action log

**Action Log Entry**:
The canonical envelope for one committed tool action in the Action Log. It is the stable shape exposed to validators and replay, independent of the physical database schema.
_Avoid_: SQLite row, proposed action

**Ask Response Flag**:
A single-use, pending-action-scoped runtime flag indicating that an ask-before rule made the agent ask the user and that a user input was observed afterward. It does not encode whether the user approved or rejected the action.
_Avoid_: approval evidence, approval state

**Pending Action**:
A proposed tool action currently being checked by MAC before execution. It may become an Action Log entry only after the host executes it and reports a tool result.
_Avoid_: log entry, committed action

**Validator Binding**:
The operational binding that tells MAC when an installed validator should run its pre-action check and post-action update logic.
_Avoid_: validator schema, validator prompt

**Validator Enforcement Shape**:
The extractor-proposed runtime shape for a rule: `check_only`, `check_update`, or `no_validator`.
_Avoid_: validator planner output, rule type

**Validator Snippet**:
A restricted Python code snippet installed for a contract, defining `update` and `check` over Pending Actions, Action Log entries, ActionLogView, and rule-local state.
_Avoid_: template validator, formal EFSM spec, unrestricted code validator

**Validator Version**:
An immutable installed validator package for a rule, tying together the snippet, state schema, bindings, sandbox policy, and ActionLog search surface used at runtime.
_Avoid_: mutable validator, latest code pointer

**Validator Verdict**:
The structured result returned by `validator.check`, expressing a local decision and its evidence for one rule against one Pending Action.
_Avoid_: final gate decision

**EFSM-like Prompting**:
A prompting discipline that asks the generator to write validator snippets as if they were small state machines with explicit state transitions and check conditions. It is not a runtime language.
_Avoid_: formal EFSM language

**Validator Snippet Verifier**:
The installer-stage module that validates a Validator Snippet's syntax, function signatures, top-level structure, and sandbox dry-run behavior before installation.
_Avoid_: validator's validator

**Validator Sandbox Runner**:
The lightweight out-of-process execution layer for Validator Snippets. It owns import, IO, API, resource, timeout, and protocol boundaries during both installation dry-run and runtime validation.
_Avoid_: static import whitelist

**ActionLogView**:
The bounded runtime helper interface a Validator Snippet may use to call `search(spec)` over committed Action Log entries, without direct SQLite access.
_Avoid_: database handle, full log scan

**ActionLog Search Spec**:
The SQL-shaped dict passed as the single argument to `ActionLogView.search(spec)`. It expresses `from`, `select`, `where`, `order_by`, and `limit` over MAC's virtual action-log schema.
_Avoid_: separate query API, raw SQL string

**ActionLogSearch Translator**:
The internal layer that compiles an ActionLog Search Spec into concrete SQLite operations over the current action-log table.
_Avoid_: raw SQL from validator snippets, physical table coupling

**Check Pattern**:
A validator binding pattern used before action execution to decide whether a Pending Action should run `validator.check`.
_Avoid_: update trigger

**Update Pattern**:
A validator binding pattern used after action execution to decide whether a committed Action Log entry should run `validator.update` to maintain rule-local state.
_Avoid_: check trigger, historical query
