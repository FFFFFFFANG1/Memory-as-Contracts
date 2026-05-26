# note.md

## User Requirements

- This is a purely memory system project (MAC = Memory-as-Contracts)
- User wants memory_design.md and implemented.md written for the **existing** core system
- The system is already fully implemented — this is documentation, not building from scratch
- The auto-memory harness will be used to improve/refine the system going forward
- plan.md should be ignored; proposal.md and README.md are the ground truth

## Agent Observations

MAC is NOT a typical agent — it IS the memory system itself. It's a contract layer
that sits beside ordinary memory systems and governs agent behavior through scoped,
lifecycle-aware behavioral contracts.

Key architecture insight: MAC is agent-agnostic. It provides:
1. Contract extraction (from user turns or cold-start sources)
2. Scope + lifecycle normalization
3. Conflict resolution with scoped edge graph
4. Prompt-intake retrieval (before planning)
5. Action-time gating (before tool execution)
6. Receipt logging (audit trail)

## Discoveries

### Components (all fully implemented):
- `models.py` — Pydantic schema: 21 models, 15 enums
- `store.py` — SQLite with FTS5, schema v1, 8 tables
- `extractor.py` — HeuristicContractExtractor + CandidateJsonContractExtractor (LLM)
- `normalizers.py` — ScopeNormalizer + LifecycleNormalizer (heuristic regex)
- `compiler.py` — PolicyCompiler: compile contracts → predicates, evaluate at action time
- `gate.py` — ActionGate: main enforcement loop (ALLOW/BLOCK)
- `retrieval.py` — PromptIntakeRetriever: 3-channel token-budgeted retrieval
- `resolver.py` — ConflictResolver: BM25+pattern similarity, LLM or heuristic relation
- `ambiguity.py` — AmbiguityMonitor (threshold=0.60, window=10) + LLMPredicateRefiner
- `matching.py` — scope_matches, lifecycle_is_active, scope_specificity
- `signatures.py` — ActionSignatureBuilder + coding_available_actions registry
- `adapters/` — ClaudeCode, Codex, Nanobot, OpenClaw (all fully implemented)
- `cli.py` — Minimal CLI (version, env, mac_rule_override)
- `config.py` — MacConfig from .env

### Integration gaps identified:
1. ConflictResolver not wired into adapter cold_start_import
2. AmbiguityMonitor not wired into gate loop
3. GateDecisionType REVISE/CONFIRM/DEFER unused
4. Hook CLI entry points (python -m ...) not implemented
5. Source refresh doesn't supersede stale contracts

### Test suite (49 tests across 7 files):
- test_models.py (11) — Pydantic validation
- test_store.py (2) — Round-trip persistence + FTS
- test_extractor_normalizers.py (8) — Heuristic + LLM extraction, normalizers
- test_core_flow.py (19) — Signatures, compiler, gate, resolver, retrieval, ambiguity
- test_adapters.py (5) — All 4 adapters: discovery, import, refresh, gating
- test_cli.py (3) — CLI integration
- test_effectiveness_live_llm.py (1) — End-to-end with real LLM

## Retention Window Mechanics

Not applicable — MAC is itself the memory layer, not an agent with a retention window.
MAC's "retention window" equivalent is the contract lifecycle and scope system that
determines which contracts are active at any given moment.

## Design Decisions

For this "self-memory" design: MAC documents itself as a memory system so that the
auto-memory refine harness can test and improve it. Each MAC component is treated as
a "memory type" with clear write/read contracts for the Critic to test.

Key architectural decision: **medium weight class** — SQLite+FTS5 persistence,
optional LLM for extraction/classification, deterministic compiled predicates for
action-time evaluation.

## Known Weaknesses

1. Gate only emits binary ALLOW/BLOCK — no nuanced enforcement
2. Adapter cold-start bypasses conflict resolution → duplicates accumulate
3. Ambiguity refinement requires manual triggering
4. Source refresh doesn't clean stale contracts from previous file versions
5. No CLI for operational debugging (extract, query, gate commands)
6. No adapter hook subprocess entry points for real host-agent integration

## Open Questions

- Should the refine harness test components in isolation or end-to-end?
  Answer: Both — per-component qa tests + e2e gating paths
- What's the priority for closing gaps?
  Answer: Gap 1 (resolver in pipeline) and Gap 2 (monitor in gate) are highest
  priority since they affect correctness of the memory system itself

## Runtime Configs

```bash
# Install
UV_CACHE_DIR=.uv-cache uv sync --dev --no-editable
cp .env.example .env
# Edit .env with OPENAI_API_KEY, MAC_LLM_MODEL, MAC_DB_PATH

# Run tests
UV_CACHE_DIR=.uv-cache uv run --no-editable pytest

# CLI
UV_CACHE_DIR=.uv-cache uv run --no-editable mac --help
UV_CACHE_DIR=.uv-cache uv run --no-editable mac version
UV_CACHE_DIR=.uv-cache uv run --no-editable mac env --json
```

## Refine Summaries
<!-- Appended at the end of refine session. Read-only during refine. -->

### Design + Implement Phase (2026-05-26)

Completed initial design and implementation documentation for the auto-memory harness:
- `memory_design.md`: Full gap analysis (6 gaps), 6 memory types with operational
  details, coverage mapping
- `implemented.md`: 15 component contracts with import paths, call signatures,
  eval_mode, persistence, and notes for the Critic
- `refine_state.json`: Initialized with step_status "ready"

The system is ready for the refine Critic to compose testable memory paths and
design a trace runner.
