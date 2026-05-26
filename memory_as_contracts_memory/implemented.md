# Memory Implementation: memory_as_contracts

## Memory Architecture

```
User turns / Memory files / Project docs
    │
    ▼
┌────────────────────────────────────────────────────────┐
│  Adapters (ClaudeCode, Codex, Nanobot, OpenClaw)       │
│  - discover_sources()                                  │
│  - cold_start_import() → Extractor → Store             │
│  - refresh_changed_sources() → re-extract changed      │
│  - build_action_signature() → ActionSignatureBuilder   │
│  - render_prompt_context() → PromptIntakeRetriever     │
│  - gate_event() → ActionGate                           │
└────────────────────────────────────────────────────────┘
    │                         │                    │
    ▼                         ▼                    ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Extraction   │  │ Prompt Retrieval │  │ Action Gate      │
│ - Heuristic  │  │ - Scope filter   │  │ - Scope/Lifecycle│
│ - LLM-backed │  │ - Lifecycle check│  │ - Edge checks    │
│ - Normalize  │  │ - Token-budget   │  │ - Compile/Eval   │
│   scope/life │  │   rendering      │  │ - Receipt logging│
└──────┬───────┘  └────────┬─────────┘  └────────┬─────────┘
       │                   │                      │
       ▼                   ▼                      ▼
┌────────────────────────────────────────────────────────┐
│  ContractStore (SQLite + FTS5)                         │
│  - contracts, edges, predicates, receipts, snapshots   │
│  - ambiguity events, refinement jobs                   │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│  ConflictResolver                                      │
│  - BM25 + pattern similarity retrieval                 │
│  - LLM or heuristic relation classification            │
│  - Precedence-based status updates                     │
│  - Scoped edge creation                                │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│  AmbiguityMonitor                                      │
│  - Threshold: ≥60% ambiguous in last 10 evaluations    │
│  - Enqueue RefinementJob                               │
│  - LLM or CopyingPredicateRefiner                      │
│  - New predicate version written to store               │
└────────────────────────────────────────────────────────┘
```

## Memory Implemented

### Package Structure
```
src/memory_as_contracts/
├── __init__.py          # Public API exports
├── models.py            # Pydantic schema (21 models, 15 enums)
├── config.py            # Env-based configuration (MacConfig)
├── store.py             # SQLite persistence (ContractStore)
├── matching.py          # Scope/lifecycle matching utilities
├── signatures.py        # ActionSignatureBuilder + coding_available_actions
├── normalizers.py       # ScopeNormalizer + LifecycleNormalizer
├── extractor.py         # Heuristic + JSON + CandidateJson extractors
├── compiler.py          # PolicyCompiler: compile + evaluate
├── gate.py              # ActionGate: deterministic gate loop
├── retrieval.py         # PromptIntakeRetriever + rendering
├── resolver.py          # ConflictResolver: dedup/supersede/conflict
├── ambiguity.py         # AmbiguityMonitor + LLMPredicateRefiner
├── cli.py               # Typer CLI (mac version|env|mac_rule_override)
└── adapters/
    ├── __init__.py      # Adapter re-exports
    ├── base.py          # BaseAdapter + ColdStartExtractor protocol
    ├── claude_code.py   # Claude Code integration
    ├── codex.py         # Codex integration
    ├── nanobot.py       # Nanobot function-bridge
    └── openclaw.py      # OpenClaw plugin-bridge
```

### Key Design Decisions

1. **SQLite + FTS5**: All state in one file; BM25 text search for similarity; JSON
   serialized Pydantic models for full fidelity.
2. **Deterministic gate**: Action-time evaluation uses compiled predicates without
   LLM calls. Only extraction and conflict resolution use LLM.
3. **Adapter-native action registries**: Each adapter declares its own
   `available_actions` and `exclude_action` list; MAC does not hardcode a global
   action enum.
4. **Scoped edges**: Conflict/supersession/exception edges have their own scope and
   lifecycle, allowing local overrides of global rules.
5. **Predicate versioning**: Compiled predicates are versioned with explicit
   `refines` pointers; the source contract text is never modified.

## Memory Type Coverage

| Memory Type | Storage Location | Write Path | Read Path |
|-------------|-----------------|------------|-----------|
| Contracts | `contracts` table + `contracts_fts` | `ContractStore.add_contract()` | `list_contracts()`, `search_contracts()`, `get_contract()` |
| Edges | `contract_edges` table | `ContractStore.add_edge()` | `list_edges()` |
| Predicates | `predicate_versions` table | `ContractStore.add_predicate_version()` | `list_predicate_versions()` |
| Receipts | `receipts` table | `ContractStore.add_receipt()` | `list_receipts()`, `receipts_by_signature_ids()` |
| Source Snapshots | `source_snapshots` table | `ContractStore.add_source_snapshot()` | `list_source_snapshots()` |
| Ambiguity Events | `ambiguity_events` table | auto via `add_predicate_evaluation()` | `recent_ambiguity_events()` |
| Predicate Evaluations | `predicate_evaluations` table | `add_predicate_evaluation()` | `recent_predicate_evaluations()` |
| Refinement Jobs | `refinement_jobs` table | `add_refinement_job()` | `list_refinement_jobs()` |

## Known Limitations

1. **Only ALLOW/BLOCK gate decisions**: REVISE, CONFIRM, DEFER are defined in the
   schema but not emitted by the gate logic.
2. **No adapter __main__ entry points**: Hook snippets reference subprocess commands
   that do not exist yet.
3. **Source refresh does not supersede old contracts**: Changed source files trigger
   re-extraction but stale contracts from previous versions persist.
4. **CLI is minimal**: Only version, env, and mac_rule_override commands exist.

## Memory Components

### Component: ContractStore

- `purpose`: Durable SQLite persistence for all MAC kernel state (contracts, edges,
  predicates, receipts, snapshots, evaluations, ambiguity events, refinement jobs)
- `write_method`:
  `from memory_as_contracts.store import ContractStore; store = ContractStore(path); store.init_db(); store.add_contract(contract)`
- `write_trigger`: system_trigger (called by extractors, gate, adapters, resolver)
- `read_method`:
  `store.list_contracts(statuses=[ContractStatus.ACTIVE])`
  `store.search_contracts("git push", limit=5)`
  `store.get_contract("MAC-xxxx")`
- `read_returns`: `list[Contract]` or `Contract | None`
- `eval_mode`: qa
- `persistence`: SQLite file at `MAC_DB_PATH` (default `.mac/contracts.sqlite`) or `:memory:`
- `requires_flush_window`: false
- `dependencies`: models
- `notes`: All store methods are synchronous. FTS5 search uses BM25 ranking. Store
  creates schema on `init_db()`. Supports `:memory:` for tests.

### Component: HeuristicContractExtractor

- `purpose`: Deterministic rule-based extraction of contracts from text using
  trigger keywords and regex classification
- `write_method`:
  `from memory_as_contracts.extractor import HeuristicContractExtractor; ext = HeuristicContractExtractor(); contracts = ext.extract_user_turn(text="Never push without asking", context=ctx)`
- `write_trigger`: system_trigger (called by adapters or test harness)
- `read_method`: N/A (extraction produces contracts, does not read from store)
- `read_returns`: `list[Contract]`
- `eval_mode`: qa
- `persistence`: none (stateless; output contracts must be stored separately)
- `requires_flush_window`: false
- `dependencies`: normalizers, models
- `notes`: Trigger keywords include "always", "never", "do not", "must", "prefer",
  etc. Filters out single-turn instructions. Classification:
  prohibition/requirement/preference/procedure. No LLM call.

### Component: CandidateJsonContractExtractor

- `purpose`: LLM-backed extraction that produces structured contract candidates with
  predicate hints, then normalizes scope/lifecycle locally
- `write_method`:
  `from memory_as_contracts.extractor import CandidateJsonContractExtractor, OpenAIChatResponseProvider; provider = OpenAIChatResponseProvider.from_env(); ext = CandidateJsonContractExtractor(provider); contracts = ext.extract_user_turn(text="...", context=ctx)`
- `write_trigger`: system_trigger (called by adapters during import/extraction)
- `read_method`: N/A (produces contracts)
- `read_returns`: `list[Contract]`
- `eval_mode`: qa
- `persistence`: none (stateless; produces contracts for store)
- `requires_flush_window`: false
- `dependencies`: normalizers, models, config (for LLM provider)
- `notes`: LLM-dependent output. Uses CONTRACT_EXTRACTION_SYSTEM_PROMPT. Supports
  custom cold_start_prompt_builder. Parses predicate_hints from LLM response into
  CompiledPredicateVersion with parameter_regex. Requires OPENAI_API_KEY and
  MAC_LLM_MODEL environment variables.

### Component: ScopeNormalizer

- `purpose`: Infers structured Scope (level, workspace, repo, path_globs, component,
  task) from natural language text
- `write_method`:
  `from memory_as_contracts.normalizers import ScopeNormalizer, NormalizationContext; norm = ScopeNormalizer(); scope = norm.normalize("Do not edit files under vendor/**", NormalizationContext(workspace="/ws", repo="proj"))`
- `write_trigger`: system_trigger (called during extraction)
- `read_method`: N/A (pure function)
- `read_returns`: `Scope`
- `eval_mode`: qa
- `persistence`: none
- `requires_flush_window`: false
- `dependencies`: models
- `notes`: Regex-based, no LLM. Detects: per_turn, component, path, task, session,
  global, repo, project. Default is project if workspace present, else global.

### Component: LifecycleNormalizer

- `purpose`: Infers structured Lifecycle (type, effective_from, expires_at,
  trigger_event) from natural language text
- `write_method`:
  `from memory_as_contracts.normalizers import LifecycleNormalizer, NormalizationContext; norm = LifecycleNormalizer(); lc = norm.normalize("This week do not push", NormalizationContext(timezone="Asia/Hong_Kong"))`
- `write_trigger`: system_trigger (called during extraction)
- `read_method`: N/A (pure function)
- `read_returns`: `Lifecycle`
- `eval_mode`: qa
- `persistence`: none
- `requires_flush_window`: false
- `dependencies`: models
- `notes`: Regex-based, no LLM. Handles "this week" (→ end of week), "today",
  "this session", "this task", "until revoked"/"always"/"from now on",
  "until <event>". Grounds relative times using context timezone.

### Component: PolicyCompiler

- `purpose`: Compiles contracts into deterministic action-time predicates and
  evaluates them against action signatures
- `write_method`:
  `from memory_as_contracts.compiler import PolicyCompiler; compiler = PolicyCompiler(); predicate = compiler.compile(contract, available_actions)`
- `write_trigger`: system_trigger (called by gate on first evaluation of a contract)
- `read_method`:
  `outcome = compiler.evaluate(predicate, signature)  # -> MatchOutcome`
- `read_returns`: `CompiledPredicateVersion` (compile) or `MatchOutcome` (evaluate)
- `eval_mode`: qa
- `persistence`: predicate versions stored in store via gate
- `requires_flush_window`: false
- `dependencies`: models
- `notes`: Deterministic, no LLM. Infers git push/commit, npm, dependency install,
  path globs from contract text. Returns AMBIGUOUS when no binding predicates exist.
  Supports tool_name exact match and parameter_regex matching.

### Component: ActionGate

- `purpose`: Deterministic action-time contract enforcement that checks all
  applicable contracts against an action signature and returns ALLOW or BLOCK
- `write_method`:
  `from memory_as_contracts.gate import ActionGate; gate = ActionGate(store, exclude_actions=["file.read"]); result = gate.gate(signature)`
- `write_trigger`: system_trigger (called by adapters before tool execution)
- `read_method`: N/A (gate is the read-and-decide path)
- `read_returns`: `GateResult` containing `GateDecision` and `Receipt`
- `eval_mode`: qa
- `persistence`: writes Receipt and PredicateEvaluation to store per gate call
- `requires_flush_window`: false
- `dependencies`: store, compiler, matching
- `notes`: Gate algorithm: (1) check exclusions, (2) iterate active contracts,
  (3) skip preferences/expired/out-of-scope, (4) check override edges, (5) check
  exception edges, (6) compile/evaluate predicate, (7) BLOCK on prohibition match
  or ambiguous/pending_conflict. Records PredicateEvaluation per evaluated contract.

### Component: PromptIntakeRetriever

- `purpose`: Compact token-budgeted retrieval of applicable contracts for prompt-time
  injection before the agent plans
- `write_method`: N/A (read-only component)
- `write_trigger`: none
- `read_method`:
  `from memory_as_contracts.retrieval import PromptIntakeRetriever, PromptRetrievalContext; retriever = PromptIntakeRetriever(store); packets = retriever.retrieve(context); text = retriever.render_prompt_text(packets, token_budget=1500)`
- `read_returns`: `list[PromptContractPacket]` or `str` (rendered text)
- `eval_mode`: hit_rate
- `persistence`: none (reads from store)
- `requires_flush_window`: false
- `dependencies`: store, matching
- `notes`: Three channels: preferences, global-rules, local-reminders. Local rules
  require target path/component hints. Token budget default 1500. Extracts path
  hints from user turn via regex (backtick paths, bare paths, file extensions,
  component names). Read-only / fixture-only for write testing.

### Component: ConflictResolver

- `purpose`: Classifies relations between new and existing contracts (duplicate,
  refinement, supersedes, conflicts_with, exception_to, independent) and applies
  status updates with scoped edges
- `write_method`:
  `from memory_as_contracts.resolver import ConflictResolver; resolver = ConflictResolver(store, relation_response_provider=llm_provider); result = resolver.insert(candidate_contract)`
- `write_trigger`: system_trigger (via `BaseAdapter._resolve_and_store` during cold-start import and source refresh)
- `read_method`: N/A (insert is the primary interface)
- `read_returns`: `ResolutionResult` containing final contract, edges, and relation
- `eval_mode`: qa
- `persistence`: writes contracts and edges to store
- `requires_flush_window`: false
- `dependencies`: store, matching
- `notes`: LLM-dependent output for relation classification (optional; falls back
  to deterministic rules). BM25 text similarity + predicate pattern overlap for
  candidate retrieval. Precedence: source authority > scope specificity > lifecycle >
  strength. Batch insert with ThreadPoolExecutor for parallel classification.

### Component: AmbiguityMonitor

- `purpose`: Detects contracts with persistently ambiguous predicate matches and
  enqueues async refinement jobs
- `write_method`:
  `from memory_as_contracts.ambiguity import AmbiguityMonitor; monitor = AmbiguityMonitor(store, window=10, threshold=0.60); job = monitor.enqueue_if_needed(contract_id, predicate_version_id)`
- `write_trigger`: system_trigger (auto-enqueued by `ActionGate` after each predicate evaluation when `auto_enqueue_refinement=True`)
- `read_method`:
  `should = monitor.should_enqueue(contract_id, predicate_version_id)`
- `read_returns`: `RefinementJob | None` (enqueue) or `bool` (should_enqueue)
- `eval_mode`: qa
- `persistence`: writes RefinementJob to store
- `requires_flush_window`: false
- `dependencies`: store
- `notes`: Threshold policy: ≥60% ambiguous in last 10 evaluations → enqueue.
  Deduplicates pending jobs for same contract+predicate. Does not block gate.

### Component: LLMPredicateRefiner

- `purpose`: LLM-backed refinement of compiled predicates to reduce ambiguity by
  generating more specific host_action_patterns and target_patterns
- `write_method`:
  `from memory_as_contracts.ambiguity import LLMPredicateRefiner, AmbiguityMonitor; refiner = LLMPredicateRefiner(response_provider); monitor = AmbiguityMonitor(store); job = monitor.run_next_pending(refiner)`
- `write_trigger`: system_trigger (called by monitor.run_next_pending)
- `read_method`: N/A (produces refined predicate versions)
- `read_returns`: `RefinementJob` with result_predicate_version_id
- `eval_mode`: qa
- `persistence`: writes new CompiledPredicateVersion to store
- `requires_flush_window`: false
- `dependencies`: store, models
- `notes`: LLM-dependent output. Uses PREDICATE_REFINEMENT_SYSTEM_PROMPT. Only feeds
  ambiguous invocation results to LLM. Produces new version with `refines` pointer.
  Falls back to CopyingPredicateRefiner (no-op version bump) when no LLM configured.

### Component: ActionSignatureBuilder

- `purpose`: Constructs normalized ActionSignature from adapter tool calls, classifying
  host_action, canonical_tags, targets, risk, and side_effect
- `write_method`:
  `from memory_as_contracts.signatures import ActionSignatureBuilder, SignatureContext; builder = ActionSignatureBuilder(); sig = builder.build(tool_name="exec", raw_arguments={"cmd": "git push origin main"}, intent="push changes", context=SignatureContext(cwd="/ws", repo="proj"))`
- `write_trigger`: system_trigger (called by adapters before gating)
- `read_method`: N/A (pure construction)
- `read_returns`: `ActionSignature`
- `eval_mode`: qa
- `persistence`: none
- `requires_flush_window`: false
- `dependencies`: models
- `notes`: Classifies exec commands into git push/commit, dependency install.
  Provides default `coding_available_actions()` registry. Deterministic, no LLM.

### Component: ClaudeCodeAdapter

- `purpose`: Integrates MAC with Claude Code agents — discovers CLAUDE.md sources,
  extracts contracts, builds hook payloads for prompt injection and tool gating
- `write_method`:
  `from memory_as_contracts.adapters import ClaudeCodeAdapter, AdapterContext; adapter = ClaudeCodeAdapter(); contracts = adapter.cold_start_import(store, extractor, context)`
- `write_trigger`: system_trigger (hook events from Claude Code)
- `read_method`:
  `prompt_ctx = adapter.render_prompt_context(store, context, user_turn="...")`
  `gate_result = adapter.gate_event(store, tool_name="exec", raw_arguments={"cmd": "git push"}, context=context)`
- `read_returns`: `dict` (hook payload) or `GateResult`
- `eval_mode`: qa
- `persistence`: contracts and snapshots written to store via import
- `requires_flush_window`: false
- `dependencies`: store, extractor, gate, retrieval, signatures, base adapter
- `notes`: Discovers `~/.claude/CLAUDE.md`, ancestor CLAUDE.md, `.claude/rules/*.md`,
  and auto-memory files. Hook output format: `permissionDecision: deny` for blocks.
  Source refresh triggered on FileChanged events.

### Component: CodexAdapter

- `purpose`: Integrates MAC with Codex agents — discovers AGENTS.md sources and
  provides hook events for prompt and gate
- `write_method`:
  `from memory_as_contracts.adapters import CodexAdapter, AdapterContext; adapter = CodexAdapter(); contracts = adapter.cold_start_import(store, extractor, context)`
- `write_trigger`: system_trigger (hook events from Codex)
- `read_method`:
  `prompt_ctx = adapter.render_prompt_context(store, context, user_turn="...")`
  `gate_result = adapter.gate_event(store, tool_name="exec", raw_arguments={"cmd": "git push"}, context=context)`
- `read_returns`: `dict` (hook payload) or `GateResult`
- `eval_mode`: qa
- `persistence`: contracts and snapshots written to store via import
- `requires_flush_window`: false
- `dependencies`: store, extractor, gate, retrieval, signatures, base adapter
- `notes`: Discovers `~/.codex/AGENTS.md`, ancestor `AGENTS.md`/`AGENTS.override.md`.
  Hook events: UserPromptSubmit, PreToolUse.

### Component: NanobotAdapter

- `purpose`: Integrates MAC with Nanobot assistants — discovers SOUL.md, USER.md,
  memory files, and provides function-bridge interface
- `write_method`:
  `from memory_as_contracts.adapters import NanobotAdapter, AdapterContext; adapter = NanobotAdapter(); contracts = adapter.cold_start_import(store, extractor, context)`
- `write_trigger`: system_trigger
- `read_method`:
  `result = adapter.gate_event(store, tool_name="send_message", raw_arguments={...}, context=context)`
- `read_returns`: `dict` with `{decision: "block"/"allow"}`
- `eval_mode`: qa
- `persistence`: contracts and snapshots written to store via import
- `requires_flush_window`: false
- `dependencies`: store, extractor, gate, retrieval, signatures, base adapter
- `notes`: Discovers SOUL.md, USER.md, memory/MEMORY.md, history.jsonl. Provides
  `build_observability_prompt_context` for manual prompt insertion.

### Component: OpenClawAdapter

- `purpose`: Integrates MAC with OpenClaw general tool-use agents — discovers
  MEMORY.md, DREAMS.md, and memory subdirectory files
- `write_method`:
  `from memory_as_contracts.adapters import OpenClawAdapter, AdapterContext; adapter = OpenClawAdapter(); contracts = adapter.cold_start_import(store, extractor, context)`
- `write_trigger`: system_trigger
- `read_method`:
  `result = adapter.gate_event(store, tool_name="document.edit", raw_arguments={...}, context=context)`
- `read_returns`: `dict` with `{block: true/false}`
- `eval_mode`: qa
- `persistence`: contracts and snapshots written to store via import
- `requires_flush_window`: false
- `dependencies`: store, extractor, gate, retrieval, signatures, base adapter
- `notes`: Discovers MEMORY.md, DREAMS.md, memory/**/*.md, project docs. Provides
  `bridge_before_prompt_build` and `bridge_before_tool_call` entry points.

### Component: MacConfig

- `purpose`: Environment-based configuration loading for API keys, model, and DB path
- `write_method`: N/A (read-only from environment)
- `write_trigger`: none
- `read_method`:
  `from memory_as_contracts.config import load_config; config = load_config(".env")`
- `read_returns`: `MacConfig` with openai_api_key, openai_base_url, llm_model, db_path
- `eval_mode`: qa
- `persistence`: reads from .env file and environment variables
- `requires_flush_window`: false
- `dependencies`: none
- `notes`: Read-only / fixture-only. Env vars: OPENAI_API_KEY, OPENAI_BASE_URL,
  MAC_LLM_MODEL, MAC_DB_PATH.
