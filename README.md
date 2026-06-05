# Memory-as-Contracts (MAC)

Memory-as-Contracts, abbreviated **MAC**, is a contract layer for memory-mediated
agent behavior.

Core idea:

> Memory is not only better context. Memory is also a contract between the user
> and the agent that constrains future behavior.

Most memory systems help agents retrieve useful context. MAC focuses on a
different problem: extracting user-stated preferences, rules, and limits from
memory, assigning each one a scope and lifecycle, and enforcing the applicable
contracts when the agent plans or takes non-excluded host actions.

This repository is now a clean **Memory-as-Contracts (MAC)** implementation. The
current Python package is `memory_as_contracts`, and the CLI entry point is
`mac`.

## What MAC Owns

MAC is not a full memory system. It is a parallel governance layer beside an
ordinary memory system.

MAC owns:

- extracting behavioral contracts from user turns and cold-start memory sources;
- normalizing scope, such as per-turn, task, session, project, path, agent family,
  organization, or global;
- normalizing lifecycle, such as this turn, this session, this week, until task
  completion, or until revoked;
- storing active, superseded, expired, rejected, and conflicting contracts plus
  scoped/lifecycle-aware edges between them;
- mapping host tool calls into action signatures through adapter hook rules;
- compiling natural-language rules into bounded predicates using the adapter's
  current available-action registry;
- asynchronously refining predicates when action-time matching is repeatedly
  ambiguous;
- checking applicable contracts before prompt planning and non-excluded actions;
- recording receipts explaining which contracts affected an action.

Existing memory systems own:

- general fact recall;
- semantic/vector/graph retrieval;
- long-term profile memory;
- ordinary task context;
- non-contractual notes, summaries, and references.

The intended flow is:

```text
user turns / memory files / project docs
  -> MAC adapters
  -> contract extraction
  -> scope + lifecycle normalization
  -> similarity + conflict check
  -> contract store and scoped edge graph
  -> prompt-intake retrieval
  -> hook-based action gate
  -> receipt log
```

## Target Agents

MAC targets two families of agents.

Coding agents:

- Claude Code-like agents (`cc`);
- Codex-like agents (`codex`).

General work agents:

- Nanobot-like personal/work assistants;
- OpenClaw-like general tool-use agents.

The first implementation can stay coding-heavy because file, command, dependency,
and git actions are easy to define and evaluate. The broader claim should still
cover general work agents where memory constrains messages, calendars, documents,
task systems, and other external tools.

## Contract Model

A MAC contract is a behavioral rule or preference with source evidence, scope,
lifecycle, and enforcement metadata.

Example:

```json
{
  "id": "MAC-001",
  "text": "This week, do not push any code changes to Git before asking me.",
  "effect": "deny",
  "authority": "user_explicit",
  "kind": "prohibition",
  "modality": "MUST_NOT",
  "strength": "hard",
  "scope": {
    "level": "project",
    "workspace": "/workspace/project",
    "agent_family": ["codex", "cc"]
  },
  "lifecycle": {
    "effective_from": "2026-05-23T09:30:00+08:00",
    "expires_at": "2026-05-30T23:59:59+08:00",
    "until_revoked": false
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
  "targets": [
    {"kind": "git_remote", "value": "*"}
  ],
  "override": {
    "allowed": true,
    "requires": "explicit_user_confirmation"
  },
  "status": "active"
}
```

`tool_patterns` and `targets` in the rule are operational seeds. The
deterministic compiler/materializer validates those seeds against the adapter's
available action registry and stores a separate `RulePatternVersion` for
action-time matching.

Initial contract kinds:

- `prohibition`: actions the agent must not take;
- `requirement`: actions or checks the agent must perform;
- `procedure`: preferred workflow or command;
- `preference`: soft style or behavior preference;
- `exception`: temporary scoped override;
- `fact`: stable information that may support reasoning but cannot authorize an
  action by itself.

## Collection Policy

For online operation, MAC should collect **user turns only** as contract sources.
Agent turns and tool outputs can provide context, but they should not become
durable user preferences unless the user confirms them.

MAC can also cold-start from existing memory and instruction sources:

- agent memory files;
- `AGENTS.md`, `CLAUDE.md`, README, and contributing docs;
- user profile memory;
- markdown, SQLite, graph, or vector memory exports.

Cold-start items must preserve source provenance and should usually have lower
freshness than current user-turn contracts.

## Restriction Points

MAC checks behavior at two points.

Prompt intake:

- retrieves compact contracts relevant to the session, project, task, and agent
  family;
- shapes planning before the agent starts acting;
- catches broad workflow rules such as "answer in chat first" or "this project is
  read-only".

Hook-based action gate:

- uses adapter-specific rules to map host tool calls into normalized action
  signatures;
- receives the adapter's current `available_actions` registry instead of relying
  on a fixed global action-class enum;
- includes current session, time, workspace, tool, target, and intent metadata in
  the signature;
- gates every action except those explicitly listed in `exclude_action`;
- returns `allow`, `revise`, `confirm`, `block`, or `defer`;
- records a receipt after the decision.

Example action signature:

```json
{
  "signature_id": "AS-102",
  "host": "codex",
  "agent_family": "codex",
  "session": {
    "session_id": "sess-20260523-001",
    "conversation_id": "conv-123",
    "turn_id": "u-018",
    "task_id": "task-auth-fix"
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

The default policy is **gate by default**. Only actions in the adapter's
`exclude_action` list may skip MAC:

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

Example adapter action registries:

- coding: `exec`, `file.read`, `file.write`, `file.delete`, `git.commit`,
  `git.push`, `dependency.install`, `web.search`;
- general work: `email.draft`, `email.send`, `message.send`,
  `calendar.create`, `document.edit`, `file.share`, `purchase.submit`,
  `task.update`, `memory.write`.

MAC can still use cross-agent canonical tags such as `external_write`,
`destructive`, `memory_write`, `publish_code`, and `notify_human`.

## Pattern Refinement

MAC should treat repeated ambiguous action-time matches as a signal that a rule's
active rule pattern version needs repair.

Default policy:

```text
if a contract is evaluated at least 10 times
and at least 60% of those evaluations are ambiguous
then enqueue async predicate refinement
```

The async job can call an LLM with the immutable rule, current rule pattern
version, adapter `available_actions`, recent ambiguous signatures, receipts, and
user confirmations. It writes a new rule pattern version, not a silent rewrite
of the source rule. Current gates do not wait for the job; high-risk ambiguous
actions should return `confirm` or `defer`, while low-risk ambiguous actions can
be allowed with a receipt according to adapter policy.

## Storage Backends

MAC should support a hybrid implementation.

Heuristic / compiled policy backend:

- compiles machine-checkable contracts into deterministic checks;
- works well for paths, commands, git, package managers, confirmation rules, and
  time-bounded bans;
- is fast and auditable.

Text + retrieval backend:

- stores contract text plus structured metadata;
- retrieves by scope, lifecycle, host action pattern, canonical tag, and lexical
  or semantic similarity;
- works better for broad workflow preferences and general-agent behavior.

The current implementation uses SQLite FTS/BM25 and deterministic gates. Embedding
retrieval can be evaluated later, but it is not required for the core claim.

## Conflict Handling

When a new contract is inserted, MAC should retrieve similar contracts and decide
whether the relation is:

- duplicate;
- refinement;
- supersession;
- conflict;
- exception;
- independent.

Duplicate handling is explicit, not incidental. MAC first checks for same-direction
high-similarity paraphrases over overlapping scope/action/tag boundaries. A
higher-authority duplicate supersedes the older rule; a lower or equal-authority
duplicate is rejected and kept only as audit evidence. Broader-but-compatible
same-direction rules are recorded as refinements instead of silently merging text.

Clear replacements may overwrite the active rule, but MAC keeps explicit edges.
Edges can also have their own scope and lifecycle. For example, a project-local
rule may supersede a global development rule only inside that project; the global
rule should remain active elsewhere.

```json
{
  "id": "E-014",
  "from_contract": "MAC-014",
  "to_contract": "MAC-003",
  "relation": "supersedes",
  "scope": {
    "level": "project",
    "workspace": "/workspace/project-1",
    "repo": "project-1"
  },
  "lifecycle": {
    "effective_from": "2026-05-23T09:30:00+08:00",
    "expires_at": null,
    "until_revoked": true
  },
  "status": "active"
}
```

MAC activates an edge only when the current action/session metadata matches the
edge scope and lifecycle. This makes the contract store explainable without
silently deleting broader rules.

## Current Implementation

The current codebase is a MAC kernel implementation:

- `memory_as_contracts` Python package;
- `mac` CLI with version and environment diagnostics;
- MAC-native environment variables: `MAC_LLM_MODEL` and `MAC_DB_PATH`;
- typed Pydantic models for rules/contracts, sources, scope, lifecycle,
  semantics, native tool patterns, rule pattern versions, scoped edges,
  available actions, action signatures, gate decisions, receipts, and ambiguity
  events;
- validation that `fact` contracts cannot bind hook enforcement patterns;
- SQLite store with schema versioning, FTS, contracts, edges, pattern versions,
  receipts, source snapshots, ambiguity events, and refinement jobs;
- LLM-backed candidate extraction with an explicit system prompt defining what
  counts as a MAC rule and what must not be extracted;
- scope and lifecycle normalization for user turns and cold-start sources;
- deterministic predicate compilation/evaluation for common coding actions;
- synchronous dedup, refinement, conflict, exception, and precedence handling
  with scoped edges;
- prompt-intake retrieval, action signature construction, deterministic gate
  decisions, receipt logging, and ambiguity-triggered predicate refinement jobs;
- pytest coverage for package, CLI, core models, store, extraction,
  normalization, resolver, retrieval, gate, receipts, and ambiguity monitoring.

It does not yet implement real host-agent hooks for Codex, Claude Code, Nanobot,
or OpenClaw; current enforcement evidence is kernel/shim-level unless a test
explicitly calls the live LLM extractor.

## Setup

```bash
UV_CACHE_DIR=.uv-cache uv sync --dev --no-editable
cp .env.example .env
```

Edit `.env` with an OpenAI-compatible API key, optional base URL, model, and
database path:

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=
MAC_LLM_MODEL=
MAC_DB_PATH=.mac/contracts.sqlite
```

For sandboxed environments where `uv` cannot use its default cache, keep the
cache inside the repo:

```bash
UV_CACHE_DIR=.uv-cache uv sync --dev --no-editable
```

## CLI

Inspect the current package and configuration:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-editable mac --help
UV_CACHE_DIR=.uv-cache uv run --no-editable mac version
UV_CACHE_DIR=.uv-cache uv run --no-editable mac env
UV_CACHE_DIR=.uv-cache uv run --no-editable mac env --json
```

Run tests:

```bash
UV_CACHE_DIR=.uv-cache uv run --no-editable pytest
UV_CACHE_DIR=.uv-cache uv run --no-editable ruff check .
```

## Roadmap

### v0: Contract Kernel

Status: in progress from a clean MAC scaffold.

- CLI and Python library;
- core schema and validation;
- write-time LLM extraction;
- SQLite store and FTS/BM25 retrieval;
- deterministic action gate;
- conflict/supersession graph;
- receipt logging.

### v0.2: Schema Alignment

- Extend the schema with explicit `scope.level`, `agent_family`, and
  `lifecycle`.
- Extend conflict/supersession edges with their own scope and lifecycle.
- Add rule pattern versions for each contract.
- Add async predicate refinement when recent action-time matches are at least
  60% ambiguous over a 10-evaluation window.
- Separate online user-turn extraction from cold-start memory import.

### v1: Agent Adapters

- Add adapters for `cc`, `codex`, `openclaw`, and `nanobot`.
- Add adapter-specific hook rule bases that map host-agent tool calls into MAC
  action signatures.
- Pass each adapter's current `available_actions` registry into MAC.
- Include session, turn, task, time, workspace, tool, target, and intent metadata
  in each action signature.
- Define an `exclude_action` list per adapter; all other actions go through MAC.
- Add prompt-intake retrieval before planning.
- Gate every non-excluded action before execution.
- Write receipts back to host-agent logs when possible.
- Support cold-start extraction from each host agent's memory files.

### v2: Evaluation

- Adapt Mem2Act for an initial memory-to-action measurement.
- Build `MACBench-Code` from coding-agent tasks plus generated rules.
- Build `MACBench-General` from MEMTRACK-like or other general-agent tasks plus
  generated rules.
- Track hard contract violation rate, scope accuracy, lifecycle accuracy,
  edge-scope/lifecycle activation, predicate match precision/recall, ambiguity
  rate before and after refinement, conflict resolution, task success, unsafe
  bypass caused by `exclude_action`, false blocks/confirmations, receipt
  correctness, token overhead, latency, and extra LLM calls.
