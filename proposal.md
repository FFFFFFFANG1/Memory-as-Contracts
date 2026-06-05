# Memory-as-Contracts (MAC) Proposal

## Core Thesis

**Memory-as-Contracts (MAC)** is a parallel memory layer for modern agents that can
take real actions. Its claim is simple:

> Memory is not only better context. Memory is also a contract between the user
> and the agent that constrains future behavior.

Most agent memory systems optimize recall: they help the agent recover facts,
preferences, prior tasks, and useful context. That framing is incomplete for
agents that edit code, run commands, send messages, schedule meetings, update
documents, or operate external tools. In these settings, some remembered user
statements are not just background information. They are behavioral constraints:

- "Never push code without asking me first."
- "For this project, do not edit files under `vendor/**`."
- "This week, any update should stay local and must not be uploaded to Git."
- "When working in my research notebook, answer in chat first; markdown is only
  for traceability."

MAC treats these statements as explicit, scoped, and lifecycle-aware contracts.
It extracts them from user turns, cold-starts from existing memory or instruction
files, resolves conflicts, and checks them at the points where an agent's behavior
is shaped or where a non-excluded host action may occur.

The goal is not to replace existing memory systems. The goal is to add the missing
governance layer:

```text
ordinary memory system:   what context might help the agent?
MAC layer:                what remembered commitments constrain this action?
```

## 1. Problem Framing

Current memory systems usually treat all memory as context. Even when they store
preferences, they often retrieve those preferences as text and let the main agent
decide how to use them. This creates several failure modes:

- **Scope failure**: a repo-specific rule is applied globally, or a global user
  preference is ignored inside a project.
- **Lifecycle failure**: a temporary instruction, such as "this week do not push",
  becomes permanent, or an expired rule is still enforced.
- **Authority failure**: an inferred memory overrides an explicit user command, or
  an old project note overrides the user's current correction.
- **Conflict failure**: two incompatible preferences are retrieved together, and
  the agent silently chooses one.
- **Action-binding failure**: the agent remembers the rule in prose but still
  performs the forbidden action because the memory was not checked at the action
  boundary.
- **Audit failure**: after an error, the user cannot tell which memory influenced
  the behavior or why it was considered applicable.

MAC's research question is therefore:

> Can we reduce memory-mediated behavioral violations by compiling user-stated
> preferences and rules into scoped, lifecycle-aware contracts, then enforcing
> them at prompt-intake and action-time boundaries?

This shifts memory evaluation from "did the agent recall more?" to "did the agent
obey the right remembered commitments in the right scope at the right time?"

## 2. Target Scenarios

MAC should be evaluated in two agent families.

### 2.1 Coding Agents

Primary coding-agent targets:

- Claude Code-like agents (`cc`);
- Codex-like agents (`codex`).

Coding agents are the cleanest first setting because actions and violations are
concrete:

- editing or deleting files;
- formatting generated files;
- running shell commands;
- installing dependencies;
- touching linked or read-only repositories;
- committing or pushing changes;
- choosing package managers and test commands;
- respecting project-specific instructions such as `AGENTS.md` or `CLAUDE.md`.

In coding, a remembered rule can be checked against a file path, command string,
working directory, git operation, or package manager. This makes the contract
layer easier to implement and evaluate.

### 2.2 General Work Agents

Primary general-agent targets:

- Nanobot-like personal/work assistants;
- OpenClaw-like general tool-use agents.

General work agents broaden the claim beyond code. Their contracts may govern:

- calendar scheduling;
- email and message sending;
- document editing;
- file organization;
- task tracking;
- purchasing or booking flows;
- research-note workflows;
- customer-support or sales operations.

These domains have messier state and broader side effects, so they should not be
the first implementation bottleneck. They are still essential for showing that
MAC is not just a coding-agent guardrail.

## 3. What MAC Stores

MAC stores **contracts**, not arbitrary memories. A contract is a remembered
behavioral statement with structured scope, lifecycle, authority, and enforcement
metadata.

### 3.1 Online Source Rule

For online extraction, MAC should collect **user turns only**. Agent turns, tool
outputs, and retrieved memories may provide context for interpretation, but they
should not become contract sources unless the user explicitly confirms them.

This rule prevents the agent from laundering its own assumptions into persistent
behavioral constraints. For example, the agent may observe that `uv` works in a
repo, but "always use uv in this repo" should either come from a project document,
a user statement, or a clearly labeled low-authority tool observation.

### 3.2 Cold Start

MAC should also support cold-start import from existing sources:

- agent memory files;
- project instruction files such as `AGENTS.md`, `CLAUDE.md`, README, or
  contributing guides;
- user profile memory;
- markdown or SQLite memory stores;
- existing preference/rule documents.

Cold-start contracts should preserve source provenance. A contract extracted from
an existing memory file is useful, but it has a different authority and freshness
profile from a current user-turn instruction.

### 3.3 Contract Schema

An initial contract object should look like this:

```json
{
  "id": "MAC-001",
  "text": "This week, do not push any code changes to Git before asking me.",
  "effect": "deny",
  "authority": "user_explicit",
  "kind": "prohibition",
  "modality": "MUST_NOT",
  "strength": "hard",
  "source": {
    "kind": "user_turn",
    "conversation_id": "conv-123",
    "turn_id": "u-017",
    "span": "这周任何更新都不要先上传git",
    "created_at": "2026-05-23T09:30:00+08:00"
  },
  "scope": {
    "level": "project",
    "workspace": "/workspace/project",
    "repo": "*",
    "path_globs": [],
    "task": null,
    "agent_family": ["codex", "cc"]
  },
  "lifecycle": {
    "effective_from": "2026-05-23T09:30:00+08:00",
    "expires_at": "2026-05-30T23:59:59+08:00",
    "until_revoked": false,
    "trigger_event": null
  },
  "semantics": {
    "actions": ["git.push"],
    "tags": ["external_write", "publish_code"]
  },
  "tool_patterns": [
    {
      "tool": "Bash",
      "args": {"command": {"regex": "^git\\s+push(\\s|$)"}}
    }
  ],
  "targets": [{"kind": "git_remote", "value": "*"}],
  "override": {
    "allowed": true,
    "requires": "explicit_user_confirmation"
  },
  "status": "active",
  "confidence": 0.94,
  "supersedes": [],
  "conflicts_with": []
}
```

The first taxonomy should stay small:

- `prohibition`: actions the agent must not take;
- `requirement`: actions/checks the agent must perform;
- `procedure`: preferred process, command, or workflow;
- `preference`: soft style or behavior preference;
- `exception`: temporary scoped override of another rule;
- `fact`: stable information that may help reasoning but cannot authorize an
  action by itself.

The `fact` boundary matters. "This repo uses uv" may support command selection.
"The user likes speed" cannot justify skipping tests, bypassing confirmation, or
editing forbidden files.

## 4. Scope and Lifecycle

The two most important MAC fields are **scope** and **lifecycle**.

### 4.1 Scope

Scope answers: where does this contract apply?

Initial scope levels:

- `per_turn`: only the current user request;
- `task`: until the current task is completed;
- `session`: current conversation/session;
- `project`: current project workspace;
- `repo`: a specific repository;
- `path`: file or folder globs;
- `agent_family`: only coding agents, only general agents, or a named adapter;
- `organization`: team/workspace-wide policy;
- `global`: user's broad preference across agents.

Scope should be normalized into machine-checkable fields whenever possible:

```json
{
  "level": "path",
  "workspace": "/workspace/research-notebook",
  "repo": "Research-Notebook",
  "path_globs": ["projects/assistant-bench/**"],
  "agent_family": ["codex"],
  "task": null
}
```

Natural language scope should not be left as prose if it can be grounded in a
workspace, repo, path, task, or adapter.

### 4.2 Lifecycle

Lifecycle answers: when is this contract active, expired, or ready for review?

Initial lifecycle types:

- `immediate`: effective now;
- `bounded_time`: e.g. "this week", "today", "until Friday";
- `bounded_session`: expires at session end;
- `bounded_task`: expires when the task completes;
- `until_revoked`: durable until the user changes it;
- `conditional`: active until an event occurs, such as "until CI passes";
- `review_after`: still active, but should be revalidated after a time or count
  threshold.

Lifecycle extraction should preserve both the normalized timestamp and the
original text span. For relative times, the system must ground the rule using the
current user timezone.

## 5. System Architecture

MAC is a parallel layer next to ordinary memory:

```text
user turns / memory files / project docs
        -> adapters
        -> contract extraction
        -> scope + lifecycle normalization
        -> contract store
        -> similarity + conflict check
        -> scoped contract-edge graph
        -> prompt-intake retrieval
        -> action-time gate
        -> receipt log
```

### 5.1 Extraction

The extractor uses an LLM to convert user turns or cold-start sources into
candidate contracts. It should output structured data, not free-form advice.

The extractor should identify:

- contract text;
- kind and modality;
- scope;
- lifecycle;
- semantic actions/tags;
- native `tool_patterns` and `targets` as operational seeds when the rule is
  hookable;
- source span;
- authority/source type;
- confidence;
- whether the statement is a durable contract or just a per-turn request.

Extraction should be followed by **contract compilation**. Compilation turns the
natural-language rule into bounded predicates that can be checked without an LLM
at action time:

```json
{
  "rule_pattern_version": {
    "version": "PV-001",
    "tool_patterns": [
      {
        "tool": "Bash",
        "args": {"command": {"regex": "^git\\s+push(\\s|$)"}}
      }
    ],
    "targets": [{"kind": "git_remote", "value": "*"}],
    "scope_predicate": {"level": "project"},
    "lifecycle_predicate": {"type": "bounded_time"}
  }
}
```

The compiler should receive the adapter's current available-action registry, so
it does not depend on a fixed global action-class enum. Extraction may provide
`tool_patterns` and `targets` as native operational seeds, but the compiler owns
adapter grounding, validation, fallback materialization, and versioning. A
coding adapter might advertise semantic actions such as `exec`, `file.read`,
`file.write`, and `web.search`; a general-work adapter might additionally
advertise `email.send`, `calendar.create`, `document.edit`, or `task.update`.
MAC can still maintain a small cross-agent tag vocabulary such as
`external_write`, `destructive`, `memory_write`, `publish_code`, and
`notify_human`, but native tool names in `tool_patterns` come from the adapter.

MAC should support periodic extraction by default. Candidate schedules:

- every 10 user turns;
- after a user+agent token threshold;
- every 5 hours in a long-running work session;
- immediately for obvious high-authority language such as "always", "never",
  "do not", "from now on", "for this project", or "this week".

The periodic schedule is an implementation policy, not the research contribution.
The contribution is that extracted items become scoped contracts rather than
undifferentiated memory text.

### 5.2 Storage and Enforcement Backends

MAC should support two complementary implementation styles.

**Heuristic / compiled policy backend**

Some contracts can be compiled into deterministic checks:

- path protections;
- git push/commit restrictions;
- dependency manager restrictions;
- generated-file edit bans;
- confirmation-before-send rules;
- time-bounded "do not upload" rules.

This backend can be implemented as explicit policy functions or if-else checks
over normalized action signatures. It is precise, auditable, and fast, but only
covers contracts that can be grounded cleanly.

**Text + retrieval backend**

Some contracts are semantic:

- communication tone;
- project workflow expectations;
- document-editing preferences;
- broad personal work habits;
- rules whose target is not reducible to a path or command.

These should be stored as text plus structured metadata, retrieved by scope,
lifecycle, host action pattern, canonical tag, and similarity. The first version
can use SQLite FTS/BM25 plus structured filters. Embeddings can be optional
later, especially for general-agent memories, but they should not be required for
the core claim.

The cleanest design is hybrid: every contract has a text record and structured
metadata; contracts that are machine-checkable additionally compile to policy
checks.

### 5.3 Adaptive Pattern Refinement

Rule pattern versions will sometimes be too broad, too narrow, or under-specified.
MAC should treat repeated ambiguous action-time matches as feedback for improving
the operational patterns.

The action gate should record a match outcome for each evaluated contract:

- `matched`: the predicate clearly applies;
- `not_matched`: the predicate clearly does not apply;
- `ambiguous`: the deterministic matcher cannot decide from the current
  signature and active rule pattern version.

For each contract version, MAC should maintain a rolling ambiguity window. A
reasonable default policy is:

```text
if evaluated_count over last window >= 10
and ambiguous_count / evaluated_count >= 0.60
then enqueue async predicate refinement
```

This refinement is asynchronous. It should not block the current action gate.
The background job can call an LLM with:

- the original contract text and source span;
- the current rule pattern version;
- the adapter's available-action registry;
- recent ambiguous action signatures;
- receipts and user confirmations when available.

The output is a new rule pattern version, not a silent rewrite of the original
rule. The source contract remains stable; only its executable pattern projection
changes. The refinement job should write a version edge such as:

```text
rule_pattern_version PV-004 refines PV-003 for MAC-014
```

While refinement is pending, ambiguous high-risk actions should return
`confirm` or `defer`; ambiguous low-risk actions may be allowed with a receipt,
depending on adapter policy.

### 5.4 Conflict and Update Handling

When a new candidate contract is extracted, MAC should first retrieve similar
contracts by text, scope, lifecycle, host action patterns, and canonical effect
tags. If a highly similar or overlapping contract exists, an LLM can classify the
relation:

- `duplicate`;
- `refinement`;
- `supersedes`;
- `conflicts_with`;
- `exception_to`;
- `independent`.

The default update policy can be overwrite/supersede for clear replacements, but
MAC must retain explicit edges. An edge is not necessarily global. It can have
its own scope and lifecycle, because the relation between two rules may only hold
inside a project, session, task, path, or time window.

For example, rule B may apply to all software development, while rule A only
replaces B inside project 1. The system should represent "A supersedes B" as a
project-scoped edge, not as a global deletion of B.

```json
{
  "id": "E-014",
  "from_contract": "MAC-014",
  "to_contract": "MAC-003",
  "relation": "supersedes",
  "scope": {
    "level": "project",
    "workspace": "/workspace/project-1",
    "repo": "project-1",
    "path_globs": []
  },
  "lifecycle": {
    "effective_from": "2026-05-23T09:30:00+08:00",
    "expires_at": null,
    "until_revoked": true
  },
  "source": {
    "kind": "user_turn",
    "span": "in project 1, follow A instead of B"
  },
  "status": "active",
  "confidence": 0.91
}
```

This edge graph keeps memory evolution explainable. A user should be able to ask
why a rule was followed and see the source, active scope, lifecycle, and conflict
history. During retrieval and gating, MAC should activate an edge only when both
the edge lifecycle and edge scope match the current action/session metadata.

Initial precedence rules:

- current explicit user turn beats older persistent memory for the current task;
- explicit user source beats project docs, tool observations, and agent inference;
- narrower scope beats broader scope;
- active lifecycle beats expired lifecycle;
- hard prohibition beats soft preference;
- bounded exception or supersession edge can override a broader rule only inside
  the edge boundary;
- unresolved equal-authority conflict becomes `pending_conflict` and forces
  clarification before affected actions.

## 6. Restriction Points

MAC should restrict agent behavior at two points.

### 6.1 User Prompt Intake

When a new user prompt arrives, MAC retrieves broad contracts relevant to the
session, project, agent family, and task. These contracts shape the agent's plan
before it starts acting.

This point catches requirements such as:

- answer in chat first;
- do not create files unless asked;
- this project is read-only;
- use a specific workflow for research notes;
- do not use a certain external service.

Prompt-intake retrieval should be compact. It should not dump the whole contract
store into context.

### 6.2 Hook-Based Action Gate

The action gate should be implemented as a host-agent hook. Before a host action
is executed, the hook uses a rule base to map the host tool call into a normalized
MAC action signature, then sends that signature to MAC for judgment.

The rule base is adapter-specific. The adapter should pass MAC both the current
host action and a current `available_actions` registry for that agent. This keeps
MAC extensible: coding agents, browser agents, and general-work agents can expose
different tool surfaces without requiring MAC to hard-code one global action
enum.

```json
{
  "signature_id": "AS-102",
  "host": "codex",
  "agent_family": "codex",
  "session": {
    "session_id": "sess-20260523-001",
    "conversation_id": "conv-123",
    "turn_id": "u-018",
    "task_id": "task-auth-fix",
    "user_id": "user-1"
  },
  "time": {
    "now": "2026-05-23T10:12:00+08:00",
    "timezone": "Asia/Hong_Kong"
  },
  "workspace": {
    "cwd": "/workspace/project",
    "repo": "project",
    "branch": "fix-auth"
  },
  "available_actions": [
    {
      "name": "exec",
      "argument_schema": {"cmd": "string"},
      "canonical_tags": ["shell", "possible_external_write"]
    },
    {
      "name": "file.write",
      "argument_schema": {"path": "string", "content": "string"},
      "canonical_tags": ["file_write", "workspace_write"]
    },
    {
      "name": "web.search",
      "argument_schema": {"query": "string"},
      "canonical_tags": ["network_read"]
    }
  ],
  "tool": {
    "name": "file.write",
    "raw_arguments": {"path": "vendor/auth.js"}
  },
  "host_action": "file.write",
  "canonical_tags": ["file_write", "source_modification", "workspace_write"],
  "targets": ["vendor/auth.js"],
  "intent": "fix failing auth test",
  "risk": "medium",
  "side_effect": "write"
}
```

MAC retrieves applicable contracts and returns:

- `allow`: the action can proceed;
- `revise`: the action should be changed before execution;
- `confirm`: ask the user before execution;
- `block`: do not execute;
- `defer`: unresolved conflict requires clarification.

The default gate policy should be **gate by default**. The adapter should expose
an `exclude_action` list containing actions that are safe to bypass. Only actions
in `exclude_action` may skip the MAC gate.

Example:

```json
{
  "exclude_action": [
    "read_file",
    "list_directory",
    "search_text",
    "inspect_git_diff",
    "pure_reasoning"
  ]
}
```

Everything outside `exclude_action` is checked by MAC, including actions that are
not obviously state-changing but can shape future behavior, such as updating a
plan, writing a memory, sharing a file, or preparing a message for send.

MAC should match rules against adapter-native `host_action` values, parsed tool
arguments, targets, and canonical tags. Example adapter action registries:

- coding: `exec`, `file.read`, `file.write`, `file.delete`, `git.commit`,
  `git.push`, `dependency.install`, `web.search`;
- general work: `email.draft`, `email.send`, `message.send`,
  `calendar.create`, `document.edit`, `file.share`, `purchase.submit`,
  `task.update`, `memory.write`.

Read-only actions are bypassed only when the adapter explicitly puts them in
`exclude_action`.

### 6.3 Receipts

Every gated action should produce a receipt:

```json
{
  "action_id": "A-102",
  "signature_id": "AS-102",
  "session_id": "sess-20260523-001",
  "decision": "confirm",
  "host_action": "git.push",
  "canonical_tags": ["external_write", "publish_code"],
  "match_outcome": "matched",
  "targets": ["origin/main"],
  "contracts_used": ["MAC-001"],
  "edges_applied": ["E-014"],
  "contracts_ignored": [
    {"id": "MAC-005", "reason": "expired"}
  ],
  "result": "awaiting_user_confirmation"
}
```

Receipts are essential for debugging and evaluation. Without receipts, the system
cannot prove that memory changed behavior for the right reason.

## 7. Repository Layout

The project should be organized around three top-level concerns:

```text
src/
  core MAC data model, extraction, normalization, conflict graph,
  retrieval, gating, receipts, and update scheduler

adapters/
  host-agent integrations and cold-start importers

eval/
  benchmark adapters, generated MAC rule/task suites, metrics, and reports
```

### 7.1 `src`

`src` should own the agent-independent contract kernel:

- schema and validators;
- LLM extraction interface;
- scope normalizer;
- lifecycle normalizer;
- contract store;
- similarity search;
- conflict resolver;
- policy compiler for heuristic checks;
- hook rule-base schema for action signature construction;
- `exclude_action` gate-bypass configuration;
- retrieval and gate logic;
- receipt logger;
- periodic update scheduler.

### 7.2 `adapters`

The first adapter set should include:

- `cc`: Claude Code-like coding agent integration;
- `codex`: Codex-like coding agent integration;
- `openclaw`: OpenClaw-like general work agent integration;
- `nanobot`: Nanobot-like personal/work assistant integration.

Adapter responsibilities:

- collect user-turns from the host environment;
- import existing memory files for cold start;
- maintain the host-specific hook rule base that maps tool calls into MAC action
  signatures;
- provide the current `available_actions` registry, including host action names,
  argument schemas, parsers, side-effect categories, and canonical tags;
- define the adapter's `exclude_action` bypass list;
- inject prompt-intake contract packets;
- enforce gate decisions before every non-excluded action;
- write receipts back to the host's logs when possible.

Cold-start import is part of adapter design. Each adapter should know where its
host agent stores memory or instructions, extract candidate constraints, and
label their authority/freshness correctly.

### 7.3 `eval`

`eval` should contain both external benchmark adaptation and MAC-specific
benchmark generation.

Initial evaluation phases:

1. **Mem2Act adaptation**: run an existing memory-to-action benchmark to test
   whether MAC improves action compliance over ordinary memory retrieval.
2. **MACBench-Code**: construct coding tasks by taking existing coding-agent
   benchmark tasks and injecting scoped/lifecycle rules.
3. **MACBench-General**: construct general-work tasks from MEMTRACK-like or
   other general-agent benchmarks, then add generated rules governing actions,
   preferences, and lifecycle.

## 8. Evaluation Design

MAC should be evaluated on rule obedience under scope and lifecycle pressure, not
only on task success.

### 8.1 Task Construction

Each benchmark item should contain:

- prior user turns or cold-start memory sources;
- generated rules/preferences with explicit hidden scope and lifecycle labels;
- current task prompt;
- environment state;
- available actions;
- expected successful task outcome;
- hidden violation oracle;
- expected or acceptable receipt.

The construction pattern is:

```text
existing benchmark task
  + generated MAC rules
  + scoped/lifecycle variants
  + action oracle
  -> contract-obedience task
```

For coding, candidate source tasks can come from SWE-bench-style repositories or
other coding-agent benchmarks. MAC variants can add:

- path-specific edit bans;
- "do not commit/push" rules;
- test-command requirements;
- package-manager restrictions;
- temporary exceptions;
- project-local vs global conflicts;
- stale instructions;
- user-change preservation rules.

For general work, candidate source tasks can come from MEMTRACK-like or broader
work-agent benchmarks. MAC variants can add:

- calendar sharing restrictions;
- email-confirmation requirements;
- document-editing preferences;
- "this week only" policies;
- session-only exceptions;
- global vs project/workspace conflicts.

### 8.2 Baselines

Recommended baselines:

- no memory;
- full transcript / long context;
- top-k memory retrieval;
- native host-agent memory;
- structured memory without a gate;
- heuristic-only MAC;
- text-retrieval-only MAC;
- hybrid MAC.

The key comparison is not whether the agent remembers more facts. It is whether
the agent violates fewer remembered behavioral contracts at similar task success.

### 8.3 Metrics

Primary metrics:

- hard contract violation rate;
- scope accuracy;
- lifecycle accuracy;
- edge scope/lifecycle activation accuracy;
- predicate match precision and recall;
- ambiguity rate before and after async predicate refinement;
- conflict resolution accuracy;
- task success rate;
- unnecessary block/confirmation rate;
- unsafe bypass rate caused by incorrect `exclude_action`;
- stale-rule harm rate;
- cold-start extraction precision and recall;
- receipt correctness;
- token overhead;
- latency overhead;
- extra LLM calls per task.

Useful derived metrics:

- violation reduction at fixed task success;
- task success at fixed violation budget;
- false-positive enforcement cost;
- percentage of violations caught at prompt-intake vs action-time.

### 8.4 Ablations

Important ablations:

- remove action-time gate and inject contracts as ordinary context;
- remove prompt-intake retrieval;
- remove scope normalization;
- remove lifecycle normalization;
- remove conflict edges;
- remove edge-level scope/lifecycle;
- replace gate-by-default with effectful-action-only gating;
- remove adaptive predicate refinement;
- replace adapter-provided available actions with a fixed global action enum;
- remove cold-start import;
- replace hybrid backend with heuristic-only;
- replace hybrid backend with text-retrieval-only;
- add embeddings to test whether they help enough to justify the added weight.

These ablations should show whether MAC's gains come from contracts, scope,
lifecycle, and action-bound enforcement rather than from cleaner memory text
alone.

## 9. Minimal Build Plan

The first useful MAC version should implement:

1. `ContractExtractor`: LLM extraction from user turns and cold-start sources.
2. `ScopeNormalizer`: maps natural language to project/repo/path/session/global
   scope.
3. `LifecycleNormalizer`: grounds temporary instructions into timestamps or
   event boundaries.
4. `ContractStore`: stores text, metadata, statuses, and scoped edge graph.
5. `SimilarityIndex`: retrieves similar rules before insert and applicable rules
   before enforcement.
6. `ConflictResolver`: LLM-assisted relation classification plus deterministic
   precedence.
7. `PolicyCompiler`: compiles machine-checkable contracts into heuristic checks
   using the adapter's available-action registry.
8. `PromptIntakeRetriever`: returns compact rules for the next agent plan.
9. `HookRuleBase`: maps host-agent tool calls into MAC action signatures with
   session/workspace/time metadata.
10. `AmbiguityMonitor`: tracks ambiguous predicate matches and enqueues async
   refinement when the last 10 evaluations are at least 60% ambiguous.
11. `ActionGate`: gates all non-excluded action signatures before execution.
12. `ReceiptLogger`: records why a contract did or did not affect behavior.
13. `Adapters`: initial `cc`, `codex`, `openclaw`, and `nanobot` bridges.
14. `EvalHarness`: Mem2Act adaptation plus generated coding/general MAC tasks.

The first paper/prototype should avoid becoming a general memory store. MAC's
center of gravity is the contract layer: extraction of behavioral commitments,
explicit scope and lifecycle, conflict-aware updates, and enforcement at the
points where the agent's behavior can change the world.
