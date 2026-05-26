# Memory Design: memory_as_contracts

## Agent Summary

Memory-as-Contracts (MAC) is not a typical agent — it IS the memory system itself.
It is a contract governance layer that sits beside ordinary memory systems and
constrains agent behavior through scoped, lifecycle-aware behavioral contracts.

MAC extracts behavioral rules from user turns and cold-start sources, normalizes
their scope and lifecycle, resolves conflicts, and enforces applicable contracts at
two decision points: prompt-intake (before planning) and action-time (before tool
execution). Every gate decision produces an auditable receipt.

The system is implemented as a Python package (`memory_as_contracts`) with:
- A typed Pydantic data model for contracts, edges, signatures, and receipts
- SQLite persistence with FTS5 for text retrieval
- Deterministic and LLM-backed extraction pipelines
- A PolicyCompiler that compiles natural-language rules into action-time predicates
- Four host-agent adapters (Claude Code, Codex, Nanobot, OpenClaw)
- An ambiguity monitoring and predicate refinement pipeline

## Gap Analysis

MAC is not a typical agent with its own retention window — it is the governance
layer that sits beside ordinary memory. The gap analysis therefore describes the
**problem in the agent ecosystem** that MAC is built to close, not internal
implementation weaknesses of this repository.

Proposal §1 frames the core mismatch:

```text
ordinary memory system:   what context might help the agent?
MAC layer:                what remembered commitments constrain this action?
```

Ordinary memory systems optimize recall. They store preferences and rules as text,
retrieve them as context, and leave the main agent to decide how to apply them.
For agents that edit code, run commands, send messages, or operate external tools,
that framing is incomplete. Some remembered user statements are not background
information — they are **behavioral constraints** that must be scoped, time-bounded,
conflict-aware, and checked at action boundaries.

### Gap 1: Scope Failure

**What information is mishandled:** Repo-specific rules applied globally, or global
user preferences ignored inside a project. A rule like "do not edit `vendor/**`"
leaks outside the repo; a project-local workflow rule never surfaces when the agent
works in that workspace.

**When:** At recall time — when retrieved memory is injected without knowing where
the agent is acting (workspace, repo, path, task, agent family).

**Impact:** Wrong rules govern the wrong actions. The agent either over-restricts
(harms task success) or under-restricts (violates user intent).

**Root cause:** Representation issue — natural-language scope left as prose instead
of machine-checkable scope fields (project, repo, path globs, task, session, global).

### Gap 2: Lifecycle Failure

**What information is mishandled:** Temporary instructions become permanent, or
expired rules are still enforced. "This week do not push" persists after the week
ends; a session-only exception outlives the session.

**When:** At write time (lifecycle not extracted) and at recall/enforcement time
(expired rules not filtered).

**Impact:** Stale constraints block legitimate actions, or time-bounded safety rules
stop protecting the user when they should still apply.

**Root cause:** Missing lifecycle normalization — relative time phrases ("this week",
"today", "until Friday") not grounded to timestamps; no active/expired filtering at
enforcement.

### Gap 3: Authority Failure

**What information is mishandled:** Inferred or stale memory overrides explicit user
commands. Agent-inferred preferences, old project notes, or cold-start doc extracts
beat a current user-turn correction.

**When:** At conflict/update time and at precedence resolution during retrieval or
gating.

**Impact:** The agent follows the wrong source of truth. User corrections are
ignored; low-authority observations become durable constraints.

**Root cause:** No provenance-aware precedence — all memory treated as equally
authoritative regardless of source kind (user_turn vs project_doc vs agent_inferred).

### Gap 4: Conflict Failure

**What information is mishandled:** Two incompatible preferences retrieved together;
the agent silently picks one. Global "always use npm" vs project-local "use uv";
"never push" vs "push hotfix when CI passes".

**When:** At write time (new rule vs existing rules) and at enforcement time
(multiple applicable contracts with opposing modalities).

**Impact:** Unpredictable behavior. The user cannot tell which rule won or why.
Equal-authority conflicts may never surface for clarification.

**Root cause:** Missing conflict graph — no explicit duplicate, supersedes,
conflicts_with, or exception_to relations with scoped/lifecycle-aware edges.

### Gap 5: Action-Binding Failure

**What information is mishandled:** The agent remembers the rule in prose but still
performs the forbidden action because memory was never checked at the action
boundary. Prompt-only injection is insufficient for hard prohibitions.

**When:** At tool execution — between planning and host action (file write, git push,
email send, etc.).

**Impact:** Memory-mediated behavioral violations despite correct recall in context.
The rule appeared in the prompt but did not bind the actual tool call.

**Root cause:** Missing action-time gate — no normalized action signature, no
compiled predicates, no deterministic check before non-excluded host actions.

### Gap 6: Audit Failure

**What information is lost:** After an error, the user cannot tell which memory
influenced behavior, which rules were considered applicable, which were ignored
(expired, out of scope, overridden), or why a block/allow decision was made.

**When:** After any gated or memory-influenced action, especially when debugging
violations or false blocks.

**Impact:** No accountability. Evaluation cannot measure "did the right contract
apply for the right reason?" Impossible to improve predicates or resolve disputes.

**Root cause:** Missing receipt log — no structured record linking action signatures,
contracts used, edges applied, match outcomes, and gate decisions.

## Design Decisions

### Weight Class

**Medium.** The system uses SQLite + FTS5 for persistence and retrieval, optional
LLM calls for extraction and conflict classification, and deterministic compiled
predicates for action-time matching. It balances precision (heuristic compilation)
with flexibility (LLM-backed extraction and refinement).

### Memory Types

MAC stores six distinct memory types, each with specific operational details:

#### 1. Behavioral Contracts (Core)

The primary memory unit. A contract is a behavioral rule or preference with source
evidence, scope, lifecycle, action constraints, compiled predicates, and status.

- **Write actor:** System-triggered (extraction pipeline) + optionally agent-triggered
  (via CLI or adapter API)
- **Write timing:** Online: during conversation when user turn contains contract
  triggers. Cold-start: at adapter initialization from existing sources.
- **Write method:** Intelligent (LLM via CandidateJsonContractExtractor) with
  heuristic fallback (HeuristicContractExtractor for obvious rules)
- **Storage form:** Typed Pydantic model serialized as JSON in SQLite, with FTS5
  index over contract text and source span
- **Update semantics:** ConflictResolver classifies as duplicate/refinement/
  supersedes/conflicts_with/exception_to/independent and creates scoped edges
- **Recall timing:** Prompt-intake (before planning) and action-time (before
  execution)
- **Recall method:** Prompt-intake: scope/lifecycle filter + text scoring. 
  Action-time: scope/lifecycle match + compiled predicate evaluation.
- **Injection point:** Prompt packets injected as structured text before planning;
  gate decisions returned before tool execution
- **Budget fit:** Prompt packets are token-budgeted (default 1500 tokens);
  action-time evaluation is deterministic (no LLM call)

#### 2. Contract Edges (Relation Graph)

Directed edges between contracts that encode update, conflict, and exception
relationships. Each edge has its own scope and lifecycle.

- **Write actor:** System-triggered (ConflictResolver during insert/batch)
- **Write timing:** When a new contract is inserted and relations are classified
- **Write method:** LLM-assisted classification with deterministic fallback
- **Storage form:** Pydantic ContractEdge serialized in contract_edges SQLite table
- **Update semantics:** Append-only with status changes (active→superseded)
- **Recall timing:** Action-time (gate checks override/exception edges)
- **Recall method:** Filter by status, match scope/lifecycle against signature
- **Injection point:** Override edges skip contracts; exception edges bypass
  prohibitions; conflict edges block until resolved
- **Budget fit:** Edge checks are deterministic O(edges × contracts)

#### 3. Compiled Predicate Versions

Versioned compilations of natural-language rules into deterministic action-time
matching predicates (host_action_patterns, target_patterns, canonical_tags).

- **Write actor:** System-triggered (PolicyCompiler during first gate evaluation
  or LLM-backed refinement)
- **Write timing:** First time a contract's predicate is needed for gating, or
  when ambiguity monitor triggers refinement
- **Write method:** Rigorous (deterministic compilation from contract text and
  action registry) + intelligent (LLM refinement for ambiguous predicates)
- **Storage form:** CompiledPredicateVersion in predicate_versions SQLite table
- **Update semantics:** New versions created with `refines` pointer to previous;
  old versions superseded
- **Recall timing:** Action-time gate evaluation
- **Recall method:** Direct lookup by contract_id
- **Injection point:** PolicyCompiler.evaluate returns MATCHED/NOT_MATCHED/AMBIGUOUS
- **Budget fit:** Pure deterministic evaluation — no LLM, no network

#### 4. Receipts (Audit Trail)

Immutable audit records of every gate decision: which contracts were checked, which
matched, what was the outcome, what edges were applied.

- **Write actor:** System-triggered (ActionGate after every decision)
- **Write timing:** After every non-excluded action gate evaluation
- **Write method:** Rigorous (deterministic construction from gate state)
- **Storage form:** Receipt model in receipts SQLite table
- **Update semantics:** Append-only, never modified
- **Recall timing:** Post-hoc analysis, ambiguity refinement, debugging
- **Recall method:** By signature_id lookup
- **Injection point:** Returned to adapter with gate decision; fed to ambiguity
  monitor for refinement prompts
- **Budget fit:** Write-only during action-time; reads are offline

#### 5. Source Snapshots

Fingerprinted snapshots of cold-start source files (CLAUDE.md, AGENTS.md, etc.)
used to detect changes and avoid redundant re-extraction.

- **Write actor:** System-triggered (adapter cold-start and refresh)
- **Write timing:** During cold-start import and source refresh
- **Write method:** Rigorous (content hash fingerprinting)
- **Storage form:** SourceSnapshot in source_snapshots SQLite table
- **Update semantics:** Upsert on source_key; fingerprint change triggers
  re-extraction
- **Recall timing:** Source refresh (compare fingerprints)
- **Recall method:** By source_key lookup
- **Injection point:** Adapter refresh flow decides extract vs skip
- **Budget fit:** Minimal — one read per source per refresh cycle

#### 6. Ambiguity Events & Refinement Jobs

Telemetry for ambiguous predicate matches and the async refinement job queue.

- **Write actor:** System-triggered (store auto-creates AmbiguityEvent on ambiguous
  PredicateEvaluation; AmbiguityMonitor creates RefinementJob)
- **Write timing:** During gate evaluation (events); during monitor check (jobs)
- **Write method:** Rigorous (deterministic threshold: ≥60% ambiguous in last 10
  evaluations)
- **Storage form:** AmbiguityEvent and RefinementJob tables in SQLite
- **Update semantics:** Events append-only; jobs transition pending→running→
  completed/failed
- **Recall timing:** After each gate evaluation (monitor check); async refinement
- **Recall method:** Recent evaluations by contract_id + predicate_version_id
- **Injection point:** Triggers predicate refinement that produces better predicates
- **Budget fit:** Monitor check is O(1) DB query; refinement uses 1 LLM call per
  job

## Gap Coverage

| Gap (proposal §1) | MAC mechanism | Why sufficient | Residual risk |
|-------------------|---------------|----------------|---------------|
| Scope failure | ScopeNormalizer + `Scope` model + `scope_matches` / `_prompt_scope_matches` at retrieval and gate | Scope normalized at write; filtered at both prompt-intake and action-time using workspace, repo, path globs, task, agent family | Path hints in user turn may be missed if not regex-extractable; component scope depends on intent/target metadata |
| Lifecycle failure | LifecycleNormalizer + `Lifecycle` model + `lifecycle_is_active` at retrieval and gate | Relative phrases grounded to timestamps; expired contracts filtered before enforcement | Session/task boundaries depend on adapter supplying session_id/task_id; conditional lifecycles need explicit trigger events |
| Authority failure | `ContractSource.kind` + ConflictResolver precedence (user_turn > project_doc > agent_inferred) + online user-turn-only extraction policy | Higher-authority sources win on duplicate/conflict; cold-start provenance preserved | Tool observations and agent-inferred text still extractable if mislabeled; user must confirm non-user sources for durable rules |
| Conflict failure | ConflictResolver + scoped `ContractEdge` graph (duplicate, supersedes, conflicts_with, exception_to) | Relations classified at insert; edges have own scope/lifecycle; gate applies override/exception edges | Equal-authority conflicts become `pending_conflict` and block — user clarification flow not fully wired in all adapters |
| Action-binding failure | ActionSignatureBuilder + PolicyCompiler + ActionGate at hook boundary; prompt-intake as secondary channel | Deterministic predicate evaluation before non-excluded actions; prohibitions block even if prompt recall failed | Soft preferences not gated; ambiguous predicates may block conservatively; REVISE/CONFIRM/DEFER not yet emitted |
| Audit failure | Receipt per gate decision + PredicateEvaluation telemetry + contracts_ignored reasons | Every gated action records contracts used, edges applied, match outcome, and ignore reasons | Prompt-intake influence not yet receipted separately; host-agent must persist returned receipt payloads |

## Open Questions

1. **Prompt-intake vs action-time split:** Which contract kinds should be enforced
   only at prompt-intake (preferences, procedures) vs only at action-time
   (prohibitions)? Current design gates prohibitions at action-time and surfaces
   preferences at prompt-intake — is that the right default for general-work agents?

2. **Semantic contracts without clean predicates:** Broad workflow rules ("answer in
   chat first") may not compile to deterministic predicates. Should these rely on
   text retrieval + prompt injection only, or eventually need embedding-backed
   matching at gate time?

3. **Source refresh and stale contracts:** When a cold-start file changes, should
   MAC supersede all contracts previously extracted from that source fingerprint,
   or re-run conflict resolution against the diff only?

4. **CONFIRM/DEFER for pending conflicts:** Equal-authority conflicts currently
   block via `pending_conflict`. Should adapters surface CONFIRM to the user before
   proceeding, and what host-agent UX is required?
