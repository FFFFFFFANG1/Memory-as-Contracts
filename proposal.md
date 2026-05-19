# Memory Use Contracts Proposal

## Core Thesis

**Memory Use Contracts** is a training-free control layer for memory-mediated agent actions.

Most agent memory systems ask whether an agent can remember and retrieve useful information. This project asks a different question: **when does a memory have the right to influence an agent action?**

The central claim is:

> Memory is not just context. Memory is a conditional right to influence future actions.

The system should not replace existing memory stores. It should sit above them, convert relevant memories into explicit contracts, check those contracts before meaningful actions, inject only the minimum applicable contract packet, and log an influence receipt explaining why memory did or did not affect the action.

The first version should use the **Standard** weight setting:

- one small LLM call when writing or normalizing memory into contracts;
- structured validation and deterministic conflict handling after extraction;
- SQLite FTS / BM25 and structured filters for retrieval;
- no embedding requirement in the core system;
- no extra LLM call before every action.

## 1. Application Scenario

The primary evaluation target should be **coding agents**, such as Codex-like and Claude Code-like agents. The broader claim can cover general tool-using agents, including OpenClaw-like agents, but the first implementation and benchmark should focus on coding.

Coding agents are the best first target because their action space is easier to define and evaluate:

- editing files;
- deleting files;
- running shell commands;
- installing dependencies;
- formatting or migrating code;
- touching read-only paths or linked repositories;
- committing or pushing changes;
- choosing project-specific test commands;
- obeying repository-local instructions.

These are exactly the places where memory misuse becomes concrete. A coding agent may remember an old test command, apply a global preference inside the wrong repo, edit a read-only linked repository, overwrite user changes, or treat a temporary exception as a permanent rule. These failures are not simply recall failures; they are failures of memory authority, scope, validity, and action binding.

General agents remain a secondary demonstration target. The same abstraction can cover calendar scheduling, email, shopping, customer support, sales operations, and research assistants. However, those domains involve broader permissions and harder-to-reproduce external effects. A first paper or prototype should therefore position coding agents as the minimal verifiable instance, then show that the contract layer is portable to general tool-using agents.

## 2. Existence Form

The system should exist as a **memory governance plugin / middleware**, not as a complete replacement memory system.

It should attach to existing memory sources:

- project instructions such as `AGENTS.md`, `CLAUDE.md`, README, contributing guides, and local rules;
- existing agent memory stores such as profile memory, auto memory, markdown notes, SQLite memory, graph memory, or vector memory;
- user instructions from the current conversation;
- tool observations that reveal stable project procedures, such as test commands or package managers.

The plugin owns only the contract layer:

```text
Existing memory / project docs / user notes
        -> Memory adapters
        -> Contract extraction and normalization
        -> Contract store and conflict graph
        -> Plan-time and action-time retrieval
        -> Contract gate
        -> Tool permission decision
        -> Influence receipt log
```

This form is important for both novelty and adoption. Existing systems already compete on how to store and retrieve memory. This project focuses on a different layer: **which memories are allowed to affect which actions under which conditions**. Users are also more likely to adopt a governance plugin than migrate their whole memory stack.

The plugin can be exposed in three practical forms:

- an SDK wrapper around agent tool calls;
- a local sidecar service with a SQLite contract index;
- a hook layer integrated into a coding agent runtime before file, shell, and git actions.

## 3. Work Mechanism

### 3.1 Main Components

The first version should contain the following components.

**Memory Adapter**

Reads raw memory and instruction sources from existing systems. It should preserve source spans so every contract can point back to the original evidence.

**Trigger Detector**

Decides when a raw event should be considered for contract extraction. It should not run extraction on every message. It should trigger on explicit durable instructions, user corrections, project rule files, stable tool observations, and session-end consolidation.

**Contract Extractor**

Uses a small LLM to convert raw events into structured candidate contracts. The small model extracts fields; it does not make the final enforcement decision.

**Schema and Source Validator**

Checks whether the extracted contract is valid JSON, has required fields, preserves a source span, and does not invent unsupported scope, action class, or authority.

**Scope and Action Normalizer**

Maps natural language scope into concrete workspace, repo, path glob, task, user, or organization scope. It also maps text into action classes such as `edit_file`, `delete_file`, `run_command`, `format_file`, `install_dependency`, `commit`, and `push`.

**Contract Store**

Stores active, candidate, superseded, rejected, and expired contracts. The first version should use SQLite plus FTS/BM25. Embeddings are not required for the core path.

**Conflict Resolver**

Builds explicit conflict and supersession relations. It should use deterministic precedence rules instead of letting the main agent freely interpret conflicts.

**Action Signature Builder**

Before a meaningful tool call, normalizes the planned action into a compact signature:

```json
{
  "action_class": "edit_file",
  "target": "linked_repos/foo/src/a.py",
  "cwd": "/workspace/project",
  "risk": "medium",
  "intent": "fix failing import"
}
```

**Contract Retriever**

Retrieves applicable contracts using structured filters first, then lexical ranking:

```text
filter: active status + action class + workspace/path/task scope
rank: authority + scope specificity + recency + BM25 match
```

**Contract Gate**

Produces a structured decision before the action:

```json
{
  "decision": "block",
  "reason": "Matches hard prohibition C-001",
  "applicable_contracts": ["C-001"],
  "allowed_override": "explicit_user_confirmation"
}
```

The gate should support:

- `allow`: no relevant contract changes the action;
- `revise`: the proposed action violates a requirement and should be changed;
- `confirm`: the action may proceed only after user confirmation;
- `block`: a hard prohibition applies;
- `defer`: unresolved contract conflict requires clarification.

**Influence Receipt Logger**

Records why memory affected, did not affect, blocked, or changed the action:

```json
{
  "action_id": "A-102",
  "action_class": "edit_file",
  "target": "src/api.py",
  "decision": "block",
  "contracts_used": ["C-021"],
  "contracts_ignored": [
    {"id": "C-002", "reason": "expired"}
  ],
  "result": "tool_executed"
}
```

Receipts are not just logs. They are the evidence needed to evaluate whether the system reduced harmful memory influence.

### 3.2 Contract Data Model

Each memory contract should be a structured object:

```json
{
  "id": "C-001",
  "text": "Do not edit files under linked repos unless explicitly asked.",
  "type": "prohibition",
  "modality": "MUST_NOT",
  "source": {
    "kind": "user_explicit",
    "span": "不要修改 linked repo",
    "created_at": "2026-05-18T10:00:00"
  },
  "scope": {
    "workspace": "current_project",
    "path_globs": ["linked_repos/**"],
    "task": null
  },
  "action_classes": ["edit_file", "delete_file", "format_file"],
  "validity": {
    "starts_at": "2026-05-18T10:00:00",
    "expires_at": null,
    "until_revoked": true
  },
  "strength": "hard",
  "confirmation": "required_to_override",
  "status": "active",
  "supersedes": [],
  "confidence": 0.96
}
```

The first version should keep the contract taxonomy small:

- `prohibition`: actions the agent must not take;
- `requirement`: actions or checks the agent must perform;
- `procedure`: project-specific process, such as how to test or format;
- `preference`: soft user or project preference;
- `exception`: scoped temporary override of another contract;
- `fact`: stable information that may support reasoning but cannot authorize action by itself.

The `fact` category needs a hard boundary. A fact can inform a decision, but it should not grant permission. For example, "this repo uses uv" can guide a test command; "the user likes speed" cannot justify skipping tests or bypassing confirmation.

### 3.3 Write Timing

The system should write or update contracts only at meaningful moments:

- The user gives a durable instruction: "以后都...", "不要再...", "这个项目默认...", "这个 repo 的规则是...".
- The user corrects the agent: "你刚才不该改那个文件", "这里应该用 uv, 不是 pip".
- The agent reads a project rule file such as `AGENTS.md`, `CLAUDE.md`, README, or contributing docs.
- A tool observation reveals a stable project procedure, such as package manager, test command, lint command, or generated artifact policy.
- The session ends or context is about to be compacted, where candidate contracts can be extracted for later review.

The write pipeline should be:

```text
raw event
  -> trigger detector
  -> small LLM contract extractor
  -> schema validator
  -> source-span check
  -> scope/action normalization
  -> conflict detection
  -> active / candidate / pending_conflict / rejected
```

The small LLM should be used only for extraction and normalization. Activation, conflict handling, expiry, and action-time decisions should be deterministic.

### 3.4 Conflict Handling

Conflicts should be first-class data, not hidden prompt ambiguity.

The first version can use these precedence rules:

- current explicit user instruction beats persistent memory for the current task;
- a narrower scope beats a broader scope: path > repo > workspace > global;
- explicit user source beats project docs, tool observations, and agent inference;
- hard prohibition beats soft preference;
- an exception must have a scope or validity boundary;
- expired contracts do not participate in the action gate;
- unresolved conflicts become `pending_conflict` and require user confirmation before affected actions.

Old contracts should not be deleted when replaced. They should be superseded:

```text
C7 supersedes C2
C2 status = superseded
```

This makes memory evolution auditable and keeps the system testable.

### 3.5 Retrieval Timing

Retrieval should happen at two levels.

**Plan-time retrieval**

Before the agent forms a plan, retrieve broad task-level contracts. For a coding task, this usually includes editing rules, test procedures, dependency policy, read-only path rules, commit/push policy, and project style constraints.

**Action-time retrieval**

Before each meaningful tool call, build an action signature and retrieve only contracts applicable to that action class and target scope. This is the core design point: memory is not poured into the context globally; it is checked at the moment it may affect an action.

After user correction or tool failure, the system should retrieve possible conflicting contracts and decide whether to update, supersede, or create a candidate contract.

## 4. Testing Outline

The evaluation should not mainly test whether the agent remembers facts. It should test whether memory correctly influences actions.

### 4.1 Benchmark Shape

The first benchmark can be **ContractBench-Code**, a coding-agent benchmark with multi-session memory and action traces. Each task should contain:

- prior memory or instruction history;
- current user request;
- repository state;
- available tool actions;
- expected action outcome;
- hidden contract oracle;
- expected influence receipt.

Useful task families:

- read-only repo or linked-repo boundary;
- "do not overwrite user changes" rules;
- repo-specific test commands;
- deprecated API migration rules;
- path-specific style or formatting rules;
- temporary exception vs permanent rule;
- conflicting local and global instructions;
- stale memory that should be ignored;
- project docs that should override generic user preference;
- actions that require confirmation, such as delete, install, commit, or push.

The benchmark should include both positive and negative cases. The system should be rewarded not only for using relevant memory, but also for refusing to use invalid, stale, weak, or out-of-scope memory.

### 4.2 Baselines

Recommended baselines:

- `No memory`: agent receives only the current task.
- `Full transcript / long context`: all previous context is provided.
- `Top-k RAG memory`: retrieve memory chunks by similarity or lexical match.
- `Structured memory without gate`: memory is normalized but not action-gated.
- `Existing agent instruction memory`: project instructions are injected as normal context.
- `Mem0 / Zep-style retrieval`: representative memory-store retrieval baseline.
- `ActMem-style actionable memory`: strong related baseline for causal/actionable retrieval.
- `MemLineage-style provenance / safety gate`: adjacent baseline for provenance-sensitive enforcement.

The key comparison is not "does the agent remember more?" but "does it cause fewer memory-mediated action failures at similar task success?"

### 4.3 Metrics

Primary metrics:

- hard contract violation rate;
- stale-memory harm rate;
- conflict resolution accuracy;
- correct action success rate;
- unnecessary confirmation rate;
- memory influence attribution accuracy;
- receipt correctness;
- token overhead;
- latency overhead;
- number of extra LLM calls per task.

The main result should be framed as:

> At similar or acceptable task success, Memory Use Contracts significantly reduces harmful memory-mediated actions, stale-rule misuse, and conflict misuse, while providing auditable receipts for how memory influenced each action.

### 4.4 Ablations

Important ablations:

- remove action-time gate and inject retrieved contracts as normal context;
- remove conflict resolver;
- remove source authority and scope specificity;
- remove expiry handling;
- replace BM25/structured retrieval with full transcript;
- replace Standard extraction with hand-written rules;
- add embeddings to test whether they help enough to justify extra weight.

These ablations should show that the gain comes from action-bound contract checking, not merely from having cleaner memory text.

## 5. Weight and Cost

The first version should implement only the **Standard** setting.

Standard means:

- use a small LLM for contract extraction at write time;
- use deterministic validators and conflict rules after extraction;
- use SQLite + FTS/BM25 + structured filters for retrieval;
- do not require embeddings;
- do not call an extra LLM at every action gate;
- store influence receipts locally;
- keep the runtime path cheap enough to wrap real coding-agent actions.

Expected cost profile:

- write cost: one small LLM call only when a durable-memory trigger fires;
- retrieval cost: local SQLite query and deterministic ranking;
- gate cost: deterministic rule evaluation;
- prompt cost: small, because only applicable contract packets are injected;
- storage cost: small structured JSON rows plus receipts;
- embedding cost: zero in the default design.

Embeddings can be evaluated later as an optional retrieval accelerator for messy general-agent memory. They should not be part of the main contribution. If embeddings become required, the work risks looking like another memory RAG system. The sharper claim is that memory governance can be effective through structured contracts, scope, source authority, validity, and action-time gating.

The first implementation should therefore avoid UI, complex graph reasoning, continuous self-reflection, and multi-agent memory debate. Those features can be future extensions, but they would blur the initial contribution.

## Minimal MVP

The minimal build should implement:

1. `ContractExtractor`: small-model extraction into JSON contracts.
2. `ContractStore`: SQLite tables plus FTS/BM25.
3. `ConflictResolver`: deterministic precedence and supersession.
4. `ActionSignatureBuilder`: normalizes file, shell, git, dependency, and test actions.
5. `ContractRetriever`: structured filters plus lexical ranking.
6. `ContractGate`: `allow`, `revise`, `confirm`, `block`, `defer`.
7. `ReceiptLogger`: records contracts used, ignored, overridden, or blocked.
8. `ContractBench-Code`: benchmark tasks where memory must correctly affect concrete coding actions.

This MVP is enough to test the core idea: whether treating memory as an action-bound contract layer reduces harmful memory influence without requiring model training or a heavy retrieval stack.
