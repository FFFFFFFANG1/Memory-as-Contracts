# Memory Use Contracts

Training-free contract layer for memory-mediated coding-agent actions.

MUC is not a full memory system. It is a governance layer that turns selected
memory, project instructions, and tool observations into explicit contracts, then
checks those contracts before effectful agent actions.

Core idea:

> Memory is not just context. Memory is a conditional right to influence future actions.

## Current v0 Behavior

v0 is a **CLI + Python library** implementation of the Standard design:

- write-time extraction uses one small OpenAI-compatible LLM call;
- action-time retrieval and gating use local SQLite FTS/BM25 plus deterministic rules;
- embeddings are not required;
- gate decisions do not call an extra LLM;
- `.env` config controls API key, base URL, model, and database path.

MUC currently does not automatically watch an agent transcript or hook into Claude
Code, Codex, or OpenClaw by itself. v0 provides file adapters and simulated
action gates so an integration can call MUC at the right moments.

v0 is complete when:

- `AGENTS.md` and `CLAUDE.md` can be imported through adapters;
- file, shell, dependency, commit, and push actions can be gated through CLI demos;
- receipts can be recorded for gated actions;
- `muc llm-check` succeeds against the configured live LLM endpoint.

v0.1 adds source snapshots for `AGENTS.md` and `CLAUDE.md`, diff-based refresh,
background refresh for use at the start of user turns, a conflict/supersession
edge table, and direct CLI writes for explicit project/file/folder/session
contracts.

## Responsibility Boundary

MUC owns:

- converting raw memory or project instructions into structured contracts;
- storing and retrieving contracts, not arbitrary memories;
- checking applicable contracts before meaningful coding-agent actions;
- returning `allow`, `revise`, `confirm`, `block`, or `defer`;
- recording influence receipts for audit and evaluation.

Existing memory systems own:

- long-term conversation memory;
- profile memory;
- ordinary semantic/vector/graph retrieval;
- raw memory collection and consolidation;
- non-contractual recall such as facts, notes, paper details, or task background.

If an existing memory system is present, the intended flow is:

```text
Existing memory system / project docs / user instructions
  -> export or surface candidate raw memories
  -> MUC extracts contracts at write time
  -> MUC stores source snapshots and conflict edges
  -> agent proposes an effectful action
  -> MUC retrieves applicable contracts from its own contract store
  -> MUC gates the action
  -> agent revises, asks confirmation, proceeds, or stops
  -> MUC records an influence receipt
```

So MUC is not just a filter over already-retrieved memory. It first compiles
action-relevant memory into contracts, then gates future actions against those
contracts. It does not replace ordinary memory RAG.

## Action-Time Gate

In the intended integration, every effectful or task-shaping tool call should go
through MUC before execution.

Gate these actions:

- `edit_file`
- `delete_file`
- `format_file`
- `run_command`
- `install_dependency`
- `commit`
- `push`
- `update_docs`

Read-only exploration can usually skip MUC:

- read file;
- search code;
- list directory;
- inspect git diff;
- ordinary reasoning;
- ordinary memory recall.

The default target mode is **effectful-only gating**: gate writes, commands,
dependency changes, and git actions, but do not gate every read-only operation.

### Gate Decisions

Action-time gate decisions are deterministic. They do not call an LLM and they do
not inject new context into the already-generated tool call. If a tool call needs
to change, MUC returns `revise` and the agent must generate a new tool call in a
later LLM turn.

Before any decision, a contract must be applicable:

- `status=active`;
- not expired by `validity`;
- `action_classes` matches the proposed tool action;
- `scope.path_globs` matches the target path when path scope is present.

Decision mapping:

| decision | Execute current tool call? | Contract condition |
|---|---:|---|
| `allow` | yes | No applicable contract requires intervention, or applicable `procedure` / `preference` / satisfied `requirement` can coexist with the call. |
| `revise` | no | Applicable `type=requirement`, `modality=MUST`, `strength=hard/soft`, `confirmation=not_required`, and the current call does not satisfy it. |
| `confirm` | no, until user confirms | Applicable contract has `confirmation=required`, including confirmable `type=prohibition`, `modality=MUST_NOT`, `strength=hard`. |
| `block` | no | Applicable `type=prohibition`, `modality=MUST_NOT`, `strength=hard`, and `confirmation` is not `required`. |
| `defer` | no | Applicable contract is unresolved, represented by `status=pending_conflict`; this is usually caused by equal-precedence conflict edges. |

Action-time gate decisions are limited to `allow`, `revise`, `confirm`, `block`,
and `defer`.

### Conflict Resolution

The resolver is intentionally conservative. It only writes conflict edges for
direct contradictions that are likely to affect the same action target. Compatible
rules such as "Use uv for tests" and "Run uv run pytest before finishing" remain
active together.

Contracts are compared only when they share:

- `status=active`;
- the same `scope.workspace`;
- at least one `action_classes` value;
- overlapping `scope.path_globs`, when both sides have path scope.

Then MUC checks whether the pair is a real contradiction:

- opposite force on the same target, such as `MUST_NOT edit vendor/**` versus
  `MUST edit vendor/**`;
- bounded `exception` contracts that explicitly target an existing rule;
- known command/package-manager conflicts, such as `use npm` versus `use uv`, or
  `not npm` versus `npm test`.

Conflict outcome table:

| Situation | Candidate status | Existing status | Edge written | Gate effect |
|---|---|---|---|---|
| Compatible contracts | `active` | unchanged | none | Both may influence later gates. |
| Changed `AGENTS.md` / `CLAUDE.md` source | `active` | old same-source contracts become `superseded` | `supersedes`, reason `source_file_refresh` | Only current source contracts are retrieved. |
| Direct contradiction, candidate has higher precedence | `active` | conflicting contracts become `superseded` | `supersedes` | Candidate governs future gates. |
| Direct contradiction, equal precedence | `pending_conflict` | unchanged | `conflicts_with` | Applicable actions return `defer`. |
| Direct contradiction, candidate has lower precedence | `rejected` | unchanged | `rejected_by` | Existing contract continues to govern. |
| Unbounded `exception` | stored without overriding permanent rules | unchanged | none unless it is also a direct bounded conflict | It does not silently authorize an action. |

Precedence is deterministic:

1. source authority: `user_explicit` > `project_doc` > `tool_observation` > `agent_inferred`;
2. narrower scope: path/task-scoped contracts outrank broad workspace contracts;
3. `strength=hard` outranks `soft` and `suggestive`.

## Source Tracking

`ingest-codex` and `ingest-cc` import instruction files once. For live use,
prefer `refresh-instructions`, which keeps an internal copy of each tracked file
and computes a diff on later runs.

```bash
uv run --no-sync muc refresh-instructions --root . --adapter all
```

On first observation, MUC ingests the full file. On later observations:

```text
stored copy + current file
  -> unified diff
  -> LLM sees diff + current full content
  -> current contracts are extracted
  -> old contracts from that source are marked superseded
  -> supersession edges are written
```

At the start of each user turn, an agent integration can run the refresh
asynchronously:

```bash
uv run --no-sync muc refresh-instructions --root . --adapter all --background
```

The background process does not block the main agent loop. Inspect tracked files
and conflict/supersession edges with:

```bash
uv run --no-sync muc snapshots
uv run --no-sync muc conflicts
```

## Direct Contract Writes

When the user explicitly states a project/file/folder/session-level contract, an
agent can write it directly without waiting for `AGENTS.md` or `CLAUDE.md`:

```bash
uv run --no-sync muc add-contract \
  --text "For this session, do not edit files unless I explicitly ask." \
  --type prohibition \
  --modality MUST_NOT \
  --strength hard \
  --confirmation required_to_override \
  --scope session \
  --action-class edit_file \
  --action-class delete_file \
  --action-class format_file
```

Do not write ordinary per-task requests such as "help me write this clearly" or
"make this answer shorter"; those are task-local instructions, not durable
contracts.

## Claude Code Example

Assume Claude Code has a `CLAUDE.md`:

```text
- Use pnpm, not npm.
- Run pnpm test before finishing.
- Do not edit files under vendor/**.
```

Import the project instructions into MUC:

```bash
uv run --no-sync muc ingest-cc --root .
```

MUC uses the configured small model to extract contracts such as:

```json
[
  {
    "type": "procedure",
    "modality": "MUST",
    "text": "Use pnpm, not npm.",
    "action_classes": ["run_command"]
  },
  {
    "type": "requirement",
    "modality": "MUST",
    "text": "Run pnpm test before finishing.",
    "action_classes": ["run_command"]
  },
  {
    "type": "prohibition",
    "modality": "MUST_NOT",
    "text": "Do not edit files under vendor/**.",
    "scope": {"path_globs": ["vendor/**"]},
    "action_classes": ["edit_file", "delete_file", "format_file"],
    "strength": "hard"
  }
]
```

Before Claude Code edits `vendor/auth.js`, a wrapper would call:

```bash
uv run --no-sync muc gate-file \
  --op edit \
  --path vendor/auth.js \
  --intent "fix failing auth test"
```

Expected decision:

```json
{
  "decision": "block",
  "reason": "Matches hard prohibition C-...",
  "applicable_contracts": ["C-..."],
  "allowed_override": "explicit_user_confirmation"
}
```

Before Claude Code runs `npm test`, a wrapper would call:

```bash
uv run --no-sync muc gate-command \
  --command "npm test" \
  --intent "run tests"
```

If the stored requirement says to use `pnpm test`, MUC should return `revise`.
The wrapper should not execute `npm test`; it should feed the gate result into
the next LLM turn so the agent can generate a corrected tool call.

## Setup

```bash
uv sync --dev --no-editable --reinstall-package memory-use-contracts
cp .env.example .env
```

Edit `.env` with an OpenAI-compatible API key, optional base URL, model, and DB
path:

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=
MUC_LLM_MODEL=
MUC_DB_PATH=.muc/contracts.sqlite
```

For sandboxed environments where `uv` cannot use its default cache, keep the
cache inside the repo:

```bash
UV_CACHE_DIR=.uv-cache uv sync --dev --no-editable --reinstall-package memory-use-contracts
```

## CLI

Initialize the local SQLite store:

```bash
uv run --no-sync muc init
```

Check the live LLM extraction path without writing to the database:

```bash
uv run --no-sync muc llm-check
```

Ingest raw memory or project instruction text:

```bash
uv run --no-sync muc ingest \
  --text "Do not edit files under linked_repos unless explicitly asked." \
  --source-kind user_explicit
```

Ingest one file:

```bash
uv run --no-sync muc ingest-file AGENTS.md --source-kind project_doc
```

Ingest Codex or Claude Code project instruction files:

```bash
uv run --no-sync muc ingest-codex --root .
uv run --no-sync muc ingest-cc --root .
```

Refresh tracked instruction files and process diffs:

```bash
uv run --no-sync muc refresh-instructions --root . --adapter all
uv run --no-sync muc refresh-instructions --root . --adapter all --background
```

Write an explicit scoped contract:

```bash
uv run --no-sync muc add-contract \
  --text "Do not edit generated files under src/generated/**." \
  --type prohibition \
  --modality MUST_NOT \
  --scope folder \
  --path "src/generated/**" \
  --action-class edit_file
```

Gate a proposed action:

```bash
uv run --no-sync muc gate \
  --action-class edit_file \
  --target linked_repos/foo.py \
  --intent "fix bug"
```

Gate file and command demos:

```bash
uv run --no-sync muc gate-file --op edit --path linked_repos/foo.py --intent "fix bug"
uv run --no-sync muc gate-command --command "git push origin main" --record
```

Inspect stored contracts and receipts:

```bash
uv run --no-sync muc contracts
uv run --no-sync muc conflicts
uv run --no-sync muc snapshots
uv run --no-sync muc receipts
uv run --no-sync muc env
```

## Live LLM Troubleshooting

`muc llm-check` must pass before calling v0 complete. It prints only non-secret
configuration and contract summaries.

If it fails:

- `OPENAI_API_KEY_SET` is false: fill `OPENAI_API_KEY` in `.env`.
- `APIConnectionError` or connection reset: check `OPENAI_BASE_URL`, local proxy,
  VPN, and provider reachability.
- `BadRequestError`: check `MUC_LLM_MODEL`; the extractor retries once without
  `response_format` if the endpoint does not support JSON mode.
- invalid JSON: the endpoint is reachable, but the model did not follow the
  contract extraction format.

## Python API

```python
from memory_use_contracts import ActionSignature, MemoryContractLayer
from memory_use_contracts.models import ActionClass, SourceKind

layer = MemoryContractLayer.from_env()
layer.init()

contracts = layer.ingest_text(
    "Do not edit files under linked_repos unless explicitly asked.",
    source_kind=SourceKind.USER_EXPLICIT,
)

decision = layer.gate(
    ActionSignature(
        action_class=ActionClass.EDIT_FILE,
        target="linked_repos/foo.py",
        intent="fix bug",
    )
)
```

## Roadmap

### v0: Contract Core Completed

Status: implemented and tested as a CLI + Python library. v0 does not claim a
real Codex or Claude Code runtime hook; it demonstrates the contract kernel and
simulated action gate.

- CLI and Python library;
- OpenAI-compatible write-time contract extraction;
- SQLite contract store and FTS/BM25 retrieval;
- deterministic retriever and action-time gate;
- influence receipt logging;
- `.env`-based configuration;
- `ingest-file`, `ingest-codex`, and `ingest-cc` adapters;
- `gate-file` and `gate-command` action demos;
- `llm-check` live extraction diagnostic;
- pytest and ruff coverage for the core path;
- optional live LLM pytest behind `MUC_RUN_LIVE_TESTS=1`.

Validation status:

- normal tests: `29 passed, 1 skipped`;
- live LLM test: passes when explicitly enabled;
- `muc llm-check`: passes against the configured `.env` endpoint.

### v0.1: Live Instruction Refresh Completed

Status: implemented for Codex and Claude Code instruction files.

- source snapshots for `AGENTS.md` and `CLAUDE.md`;
- diff-based refresh using stored copy + current file;
- changed instruction files send diff + current full content to the write-time
  LLM extractor;
- old same-source contracts are marked `superseded`;
- supersession edges are written to the conflict graph;
- `refresh-instructions --background` supports async refresh at the start of a
  user turn;
- `snapshots` and `conflicts` inspect source copies and graph edges;
- `add-contract` lets an agent write explicit project/file/folder/session-level
  contracts without waiting for instruction files;
- `skills/muc-contract-writer/SKILL.md` documents when to write a direct contract
  and when to treat user text as task-local.

### v0.2: CLI Polish

Useful next hardening before a real hook:

- add `ingest-json` for exported memory items;
- expose a dry-run command that shows extracted contracts before storing them;
- improve receipt detail for ignored, expired, and superseded contracts;
- add a conflict-resolution CLI for accepting one side or superseding a contract;
- install or copy `skills/muc-contract-writer/SKILL.md` into a Codex skill path
  if you want it globally available outside this repo.

### v1: Coding-Agent Integration

Goal: make MUC usable as a plugin/hook layer for Codex-like and Claude Code-like
agents.

- Provide a wrapper API around real effectful tool calls.
- Gate file writes, command execution, dependency installation, formatting,
  commit, and push before execution.
- Add plan-time retrieval for broad task-level constraints before agent planning.
- Add action-time retrieval for precise path/action contracts before tool execution.
- Record receipts automatically after each gated action.
- Run `refresh-instructions --background` automatically at user-turn boundaries.
- Feed `revise`, `confirm`, `block`, and `defer` decisions into the next agent
  LLM turn in the host-agent-native format.

### v2: Evaluation Harness

Goal: test whether action-bound contracts reduce harmful memory influence.

- Build `ContractBench-Code`.
- Include read-only repo boundaries, stale instructions, conflicting local/global
  rules, temporary exceptions, path-specific test commands, and user-change
  preservation tasks.
- Compare against no memory, full transcript, top-k memory retrieval, structured
  memory without gate, and existing instruction-memory baselines.
- Track hard contract violation rate, stale-memory harm, task success,
  unnecessary confirmation, receipt correctness, token overhead, and latency.

### v3: Broader Agent Adapters

Goal: demonstrate that the layer generalizes beyond coding agents without making
v0 heavy.

- Add optional adapters for general tool-using agents.
- Add optional memory-store adapters for systems such as SQLite memory, markdown
  memory, graph memory, or vector memory.
- Evaluate whether embeddings help messy general-agent memories enough to justify
  adding them as an optional retrieval accelerator.
- Keep the default core path training-free and non-embedding-based.
