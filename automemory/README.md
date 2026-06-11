# AutoMemory MAC Traces

This directory contains critic-style grey-box traces for the current
Memory-as-Contracts implementation. The suite focuses on observable MAC behavior
across ingestion, storage, retrieval, action gating, conflict edges, adapter
hooks, and Stage 2 validator runtime.

Run from the repository root:

```bash
UV_CACHE_DIR=.uv-cache uv run python automemory/run_traces.py
```

For a machine-readable report:

```bash
UV_CACHE_DIR=.uv-cache uv run python automemory/run_traces.py --json
```

To run the LLM-honest mode for MAC itself, using the live extractor and
validator/coder configured in `.env`:

```bash
UV_CACHE_DIR=.uv-cache uv run python automemory/run_traces.py --llm --json
```

The runner exits with a non-zero status if any trace scores below 1.0. That is
intentional: these traces are designed to expose MAC weaknesses, not just confirm
happy paths.

## Trace Coverage

- `trace_id_ingestion_online_batch_to_prompt`: ten-turn user batching to online extraction and prompt retrieval.
- `trace_id_cold_start_project_doc_once`: Codex project instruction cold-start import and snapshotting.
- `trace_id_retrieval_scope_context_shift`: prompt-intake retrieval under path and workspace scope shift.
- `trace_id_gate_native_patterns_and_exclusions`: deterministic signature building, native tool patterns, and exclusions.
- `trace_id_resolver_authority_conflict_edges`: conflict resolution and scoped edge persistence.
- `trace_id_validator_check_only_test_before_push`: check-only validator over bounded Action Log search.
- `trace_id_validator_check_update_budget_state`: check-update validator state accumulation and rejection.
- `trace_id_adapter_ask_response_single_use`: adapter-level ask request lifecycle and same-turn retry.
- `trace_id_e2e_online_to_gate_receipts`: end-to-end online extraction through adapter gate receipts.
