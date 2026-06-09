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
A single-use, pending-action-scoped runtime flag indicating that the gate returned
`ask` and MAC observed the immediately following user input. MAC does not decide
what the user's instruction means; interpreting that instruction and deciding
what action to propose is the main agent's responsibility. When the immediately
following Pending Action matches the same rule in the same session/task and
native tool family, MAC assumes the main agent performed the required ask and
skips only that rule once. The flag does not encode whether the user approved or
rejected the action, and all other rules are still evaluated.
_Avoid_: approval evidence, approval state

**AskRequest**:
The persisted lifecycle record for an `ask` decision: `required`, `responded`,
`consumed`, or `cancelled`. `UserPromptSubmit` moves the latest same-scope
`required` request directly to `responded`. It stores scope, exact native tool
name, related rules, response turn, and TTL, but never the user's response
content. MAC intentionally does not require a separate observable assistant-ask
event: the adjacent user turn followed by a same-rule retry is the operational
evidence used at this boundary.
_Avoid_: approval record, user response memory

**Gate Decision**:
The final action-time result after exception/override handling and local verdict
aggregation. The only values are `allow`, `reject`, and `ask`, ordered
`reject > ask > allow`.
_Avoid_: block, confirm, revise, defer

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

**Validator Scope Key**:
A deterministic key whose dimensions are selected by the contract scope level:
per-turn uses session/task/turn, task uses session/task, session uses session,
project uses workspace, repo/path use workspace/repo, organization uses
organization, and global uses user identity. Validator state is keyed by
validator version plus this scope key and updated with a revision check.
_Avoid_: global validator state, contract-id-only state

**Periodic User-Turn Extraction**:
The online ingestion policy that persists user turns and sends each batch of ten
unprocessed turns to the Rule Extractor. Successful candidates pass through the
Conflict Resolver into the Contract Store; the Action Gate never calls the
extractor.
_Avoid_: action-time extraction, assistant-turn extraction

**Tool Pattern**:
An adapter-native operational matcher over an exact tool name and raw argument
fields. Rule schemas do not have a separate `targets` field; paths, URLs,
resources, and other enforceable operands belong in tool argument matchers.
Observed targets may still appear in Action Signatures, Action Log entries, and
receipts as audit/scope metadata.
_Avoid_: semantic action, declarative target pattern

**Pattern Verifier**:
The deterministic ingestion-time check applied to extractor-proposed
`tool_patterns`, `check_patterns`, and `update_patterns`. It verifies that each
native tool and argument exists in the adapter capsules, text matchers are
compatible with the argument schema, and every regex compiles. A failed proposal
may receive at most one synchronous LLM refinement and is then reverified.
Rules that still fail remain `candidate` and cannot install an active pattern
version.
_Avoid_: ambiguity monitor, refinement queue, action-time LLM repair

**Pattern Compiler**:
The deterministic materializer that turns verified rule fields into a
`RulePatternVersion`. It depends on `tool_patterns`, semantics, scope, lifecycle,
and optional workspace grounding, not on the adapter `available_actions` registry.
Native tool/argument validity is enforced earlier by the Pattern Verifier using
Tool Capsules. `available_actions` remains ActionSignature/receipt context.
_Avoid_: available-actions matcher, tool-schema verifier

**Pattern Match Outcome**:
The deterministic action-time result of a verified Tool Pattern. The only values
are `matched` and `not_matched`. Missing arguments and nonmatching values are
`not_matched`; invalid regexes never reach the gate because the Pattern Verifier
rejects them during ingestion.
_Avoid_: ambiguous

**Check Pattern**:
A validator binding pattern used before action execution to decide whether a Pending Action should run `validator.check`.
_Avoid_: update trigger

**Update Pattern**:
A validator binding pattern used after action execution to decide whether a committed Action Log entry should run `validator.update` to maintain rule-local state.
_Avoid_: check trigger, historical query
