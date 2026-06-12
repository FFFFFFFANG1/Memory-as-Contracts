# Constraint Memory Benchmark Build Plan

Audience: future coding agents working in this repository.

Source of truth: `constraint_memory_benchmark_research.md`.

Current prep state:

- Benchmark sources are checked out under `bench/sources/`.
- Agent scaffolds are checked out under `bench/agents/`.
- `bench/source_lock.json` records pinned source revisions.
- API keys, base URLs, and model IDs must come from the repository root `.env`.
- The general workflow source is **tau3-bench**, distributed from the upstream
  `tau2-bench` repository. Keep the internal adapter id `tau`.

## Non-Negotiable Constraints

- Do not evaluate base-task solving ability at benchmark time. Evaluation is
  offline trajectory-prefix action QA only.
- Gold labels come only from deterministic hidden contract-graph resolution.
- Do not add QA queries or answers back into memory during evaluation.
- Do not use future trajectory events at a QA position.
- Do not splice successful trajectory segments from different runs.
- Each source task or history pack gets at most two trajectory-generation runs:
  GLM-5.1 first, Kimi-K2.6 fallback.
- Do not vendor upstream datasets, repository images, generated caches, database
  files, or trajectories into git.
- Keep fixed-reader prompt, retrieval budget, current-state summaries, and
  evaluation protocol identical across systems.

## Task 0: Reconcile Workspace Layout

Goal: create the local benchmark implementation package without disturbing
checked-out upstream source repositories.

Steps:

- [ ] Create `benchmarks/` implementation tree from the layout in the research
  doc.
- [ ] Keep `bench/` for local upstream checkouts and caches.
- [ ] Add `benchmarks/source_lock.json` by copying/adapting
  `bench/source_lock.json`.
- [ ] Add `benchmarks/data_card.md` skeleton with license and redistribution
  warnings.
- [ ] Confirm `.gitignore` excludes heavy generated artifacts.

Done when:

- `benchmarks/` exists with empty source adapter modules and schemas.
- Source locks include SCBench runner/problems, SWE-bench, ToolSandbox,
  tau3-bench-from-`tau2-bench`, OpenHands, and OpenCode.

## Task 1: Define Canonical Schemas

Goal: make all benchmark artifacts schema-valid before implementing generation.

Steps:

- [ ] Add `benchmarks/schemas/contract_graph.schema.json`.
- [ ] Add `benchmarks/schemas/canonical_event.schema.json`.
- [ ] Add `benchmarks/schemas/canonical_action.schema.json`.
- [ ] Add `benchmarks/schemas/history_pack.schema.json`.
- [ ] Add `benchmarks/schemas/qa_item.schema.json`.
- [ ] Implement Python models or validators that load and validate these
  schemas.
- [ ] Add fixture examples for one minimal trajectory and one QA item.

Done when:

- Tests fail on malformed modality, lifecycle, action family, missing source
  provenance, and invalid `allow|reject|ask` labels.
- Tests pass on hand-written valid fixtures.

## Task 2: Implement Contract Oracle

Goal: deterministically resolve active behavioral contracts for one proposed
action at one prefix.

Steps:

- [ ] Implement `benchmarks/contracts/scope.py`.
- [ ] Implement `benchmarks/contracts/lifecycle.py`.
- [ ] Implement `benchmarks/contracts/predicates.py`.
- [ ] Implement `benchmarks/contracts/resolver.py`.
- [ ] Support node modalities: `must`, `must_not`, `may`, `prefer`,
  `ask_before`.
- [ ] Support edge types: `exception_to`, `overrides`, `supersedes`,
  `refines`, `conflicts_with`, `independent`.
- [ ] Explicitly reject any hidden global rule such as "newer always wins"
  unless encoded by contract text or edge.
- [ ] Return gold decision plus active contract ids and decisive relation ids.

Done when:

- Table-driven tests cover scope selection, temporal activation, revocation,
  narrow exception, override, supersession, refinement, unresolved conflict,
  and independent distractors.
- Hand-written graphs produce unique deterministic labels.

## Task 3: Implement Canonical Metrics

Goal: compute the required benchmark scores from QA predictions.

Steps:

- [ ] Implement `benchmarks/evaluation/metrics.py`.
- [ ] Compute Contract Decision Accuracy.
- [ ] Compute decision macro-F1.
- [ ] Compute per-label recall for `allow`, `reject`, and `ask`.
- [ ] Compute violation escape rate: gold `reject`, predicted `allow`.
- [ ] Compute false block rate: gold `allow`, predicted `reject`.
- [ ] Compute evidence-turn Recall@K.
- [ ] Compute active-contract F1 and decisive-relation F1.
- [ ] Compute paired counterfactual accuracy.
- [ ] Add 95% bootstrap confidence intervals.

Done when:

- Metrics match small hand-computed fixtures.
- Missing optional predicted ids do not break decision scoring.

## Task 4: Build Trajectory-Prefix Harness

Goal: run online-prefix memory construction without leakage.

Steps:

- [ ] Implement canonical JSONL event storage.
- [ ] Implement incremental prefix ingestion.
- [ ] Implement QA position markers.
- [ ] Implement fixed-reader input/output envelope.
- [ ] Implement event-group ids for related variants.
- [ ] Implement split ids.
- [ ] Implement `benchmarks/evaluation/online_prefix_runner.py`.
- [ ] Add no-future-event assertions.

Done when:

- A synthetic ten-event trajectory evaluates three QA positions correctly.
- The QA query and answer are never added to memory.
- Systems that rebuild from prefix receive exactly the same content as online
  ingestion would have seen.

## Task 5: Implement Fixed Reader

Goal: isolate memory retrieval quality from answer formatting.

Steps:

- [ ] Implement `benchmarks/evaluation/fixed_reader.py`.
- [ ] Load provider config from `.env`.
- [ ] Use temperature zero.
- [ ] Enforce the main retrieval-output budget of 2K tokens.
- [ ] Return JSON with `decision`, optional `active_contract_ids`, and short
  reason.
- [ ] Add parser repair only for trivial JSON formatting issues, not label
  ambiguity.

Done when:

- A reader call with oracle evidence reaches expected answers on fixtures.
- Failed JSON is recorded as an evaluation error with source metadata.

## Task 6: Build Generation Utilities

Goal: produce contract graphs, natural insertions, action variants, and QA text
with reusable tooling.

Steps:

- [ ] Implement `benchmarks/generation/graph_generator.py`.
- [ ] Implement `benchmarks/generation/realization_generator.py`.
- [ ] Implement `benchmarks/generation/counterfactual_generator.py`.
- [ ] Implement `benchmarks/generation/qa_renderer.py`.
- [ ] Store prompts from the research doc as versioned templates.
- [ ] Hash system prompt, task prompt, source adapter version, and model config.
- [ ] Add generation manifests for every produced artifact.

Done when:

- Generated candidates include provenance, prompt hashes, model ids, and source
  revisions.
- LLM generation output is treated as candidate material only, never gold.

## Task 7: Build QA Construction and Validation

Goal: select observable action positions and filter candidates before pilots.

Steps:

- [ ] Implement `benchmarks/qa/position_sampler.py`.
- [ ] Implement `benchmarks/qa/state_summarizer.py`.
- [ ] Implement `benchmarks/qa/build_items.py`.
- [ ] Implement `benchmarks/qa/blinded_checks.py`.
- [ ] Implement `benchmarks/qa/human_review_export.py`.
- [ ] Enforce variant families: original action, minimal violation, legal
  near-miss, scope counterfactual, temporal counterfactual, missing
  authorization or information.
- [ ] Keep variants from one event group in the same split.
- [ ] Record progress position, prefix tokens, evidence distance, intervening
  contract events, and variant type.

Done when:

- Every QA candidate passes schema validation and deterministic graph
  resolution.
- Filters reject non-observable actions, future-evidence dependence, query
  leakage, assistant echo leakage, trivial query-only items, and ambiguous
  oracle-evidence items.

## Task 8: Implement Source Adapter Interface

Goal: make four sources expose a common lifecycle.

Steps:

- [ ] Define adapter protocol: `fetch`, `select`, `overlay_or_pack`, `run`,
  `normalize`, `validate`.
- [ ] Define canonical event fields for messages, tool calls, observations,
  state snapshots, file summaries, timestamps, and action effects.
- [ ] Define source-task validation result schema.
- [ ] Define contract-audit result schema.
- [ ] Add tests with fake adapters.

Done when:

- The common harness can run a fake source adapter end-to-end.
- Adapter failures record whether they consume a run budget.

## Task 9: SCBench Pilot

Goal: produce at least 20 accepted SCBench QA covering all labels.

Steps:

- [ ] Implement `benchmarks/sources/scbench/fetch.py` against local
  `bench/sources/scbench-runner` and `bench/sources/scbench-problems`.
- [ ] Select two SCBench problems with multiple scopes and enough observable
  actions.
- [ ] Decompose native checkpoints into bounded cumulative subtasks.
- [ ] Write or select subtask acceptance tests.
- [ ] Verify requirement coverage and equivalence to original checkpoint tests.
- [ ] Author one hidden contract graph per selected problem.
- [ ] Realize contracts through subtasks, project docs, user follow-ups, and
  review feedback.
- [ ] Run OpenCode with GLM-5.1; fallback once to Kimi-K2.6 if needed.
- [ ] Validate subtasks, checkpoint tests, regression tests, and contract audit.
- [ ] Normalize trajectory events and actions.
- [ ] Produce 20-30 candidate QA.
- [ ] Run automatic validators and blinded checks.

Done when:

- At least 20 SCBench QA are accepted.
- `allow`, `reject`, and `ask` are all represented.
- At least one lifecycle-changing relation affects a later decision.

## Task 10: SWE-bench Verified Pilot

Goal: produce at least 20 accepted SWE-bench QA from three repositories.

Steps:

- [ ] Implement `benchmarks/sources/swebench_verified/fetch.py`.
- [ ] Fetch metadata and prepare official images outside git-tracked files.
- [ ] Select three easy Verified tasks from different repositories.
- [ ] Create natural issue or maintainer overlays.
- [ ] Verify at least one legal solution remains after overlays.
- [ ] Run OpenCode with GLM-5.1; fallback once to Kimi-K2.6 if needed.
- [ ] Validate final patch against `FAIL_TO_PASS` and `PASS_TO_PASS`.
- [ ] Audit all executed actions against hidden contract graph.
- [ ] Normalize messages, tool calls, observations, patch states, and actions.
- [ ] Produce 20-30 candidate QA.
- [ ] Run automatic validators and blinded checks.

Done when:

- At least 20 SWE-bench QA are accepted from at least three repositories.
- Labels come from the graph, not the gold patch.
- Proposed actions identify target file/component and intended effect.

## Task 11: ToolSandbox Pilot

Goal: produce at least 20 accepted ToolSandbox QA covering all labels.

Steps:

- [ ] Implement `benchmarks/sources/toolsandbox/fetch.py`.
- [ ] Select five deterministic local-tool scenarios.
- [ ] Create two persistent user history packs with consistent user state.
- [ ] Introduce contracts through normal user requests.
- [ ] Run OpenHands with GLM-5.1; fallback once to Kimi-K2.6 if needed.
- [ ] Validate official milestone DAGs.
- [ ] Capture pre-tool-call state snapshots.
- [ ] Normalize tool calls and state summaries.
- [ ] Produce 20-30 candidate QA.
- [ ] Verify missing-information cases genuinely require `ask`.

Done when:

- At least 20 ToolSandbox QA are accepted.
- State summaries are sufficient but do not reveal hidden contract answers.
- Proposed actions are expressible through real tools.

## Task 12: tau3-bench Pilot

Goal: produce at least 20 accepted tau3-bench QA across retail, airline, and
telecom.

Steps:

- [ ] Implement `benchmarks/sources/tau/fetch.py` against local
  `bench/sources/tau2-bench`.
- [ ] Pin the exact tau3-bench release and record it in source lock.
- [ ] Select text-mode tasks from retail, airline, and telecom.
- [ ] Exclude voice/full-duplex tasks and knowledge-retrieval-dominated tasks.
- [ ] Separate always-visible upstream policy from dynamic memory contracts.
- [ ] Create two organization history packs with policy and database
  consistency.
- [ ] Run OpenHands with GLM-5.1 and the official user simulator; fallback once
  to Kimi-K2.6 if needed.
- [ ] Validate original task reward/evaluator.
- [ ] Normalize tool calls, communication actions, and database summaries.
- [ ] Produce 20-30 candidate QA.
- [ ] Verify `ask` cases identify missing authorization or unresolved conflict.

Done when:

- At least 20 tau3-bench QA are accepted across the three target domains.
- Every QA requires both current upstream policy and dynamic history contracts.

## Task 13: Pilot Audit

Goal: decide whether to scale beyond pilots.

Steps:

- [ ] Combine 80-100 accepted pilot QA.
- [ ] Run all automatic validators.
- [ ] Export complete human-review packet.
- [ ] Run query-only, evidence-removed, oracle-evidence, and canonical-graph
  checks.
- [ ] Run BM25, dense, hybrid, full-prefix, MAC, and oracle baselines.
- [ ] Produce preliminary position, prefix-length, evidence-distance, and
  interference curves.
- [ ] Check source-level label and relation coverage.

Done when:

- Oracle evidence decision accuracy is at least 95%.
- Oracle graph decision accuracy is at least 98%.
- Query-only performance is materially below memory baselines.
- Evidence-removed performance is close to query-only.
- Human decision agreement is at least 0.80.
- Realism and recoverability agreement are at least 0.70.
- No single source drives the benchmark result.

## Task 14: Scale Candidate Generation

Goal: build enough candidates to release roughly 500 final QA.

Steps:

- [ ] Scale each source independently to 150-180 candidates.
- [ ] Maintain a live quota table by source, split, label, relation pattern,
  progress bin, evidence-distance quartile, action family, and contract source.
- [ ] Stop generation for overrepresented cells.
- [ ] Ensure target final shares: 125 QA per source, about 250 coding and 250
  general.
- [ ] Ensure label targets: 200 `allow`, 175 `reject`, 125 `ask`, each with
  tolerance +/- 20.
- [ ] Ensure at least 25% of QA belong to matched retention pairs.
- [ ] Ensure all sources contribute all three labels.

Done when:

- Filtering leaves approximately 500 QA, tolerance +/- 20.
- No source contributes fewer than 110 final items.
- All five progress bins are meaningfully represented.

## Task 15: Split Dataset

Goal: create leakage-safe development, public test, and hidden test splits.

Steps:

- [ ] Split by source task, repository/project, history pack, contract graph,
  and event group.
- [ ] Keep variants, prefixes, and runs from one underlying task in the same
  split.
- [ ] Target per source: 25 dev, 50 public test, 50 hidden test.
- [ ] Prefer repository-level separation for SWE-bench where feasible.
- [ ] Export `benchmarks/releases/v1/dev.jsonl`.
- [ ] Export `benchmarks/releases/v1/public_test.jsonl`.
- [ ] Export `benchmarks/releases/v1/hidden_test_inputs.jsonl`.

Done when:

- Split leakage tests pass.
- Hidden test inputs exclude gold labels, evidence ids, graph nodes, and
  future events.

## Task 16: Run Final Baselines

Goal: produce the main evaluation table under a fixed reader and 2K retrieval
budget.

Steps:

- [ ] Run naive long-context baseline.
- [ ] Run BM25 retrieval over turns/events.
- [ ] Run dense retrieval over turns/events.
- [ ] Run hybrid BM25+dense.
- [ ] Run mem0.
- [ ] Run a-mem.
- [ ] Run letta or zep.
- [ ] Run openclaw-style memory.
- [ ] Run claude-code-style memory if locally available.
- [ ] Run MAC.
- [ ] Record memory build cost, retrieval latency, and reader tokens.

Done when:

- Every baseline uses the same fixed reader, same retrieval-output budget, same
  current-state summaries, and no query-time memory updates.
- Main metrics and confidence intervals are generated.

## Task 17: Generate Analysis Artifacts

Goal: prepare plots and tables required by the paper.

Steps:

- [ ] Plot accuracy versus normalized trajectory position.
- [ ] Plot accuracy versus prefix-token bins computed after data collection.
- [ ] Plot accuracy versus evidence-distance quartile.
- [ ] Plot accuracy versus number of intervening contract events.
- [ ] Plot accuracy before and after override, revocation, or exception events.
- [ ] Report natural trajectory-token distribution.
- [ ] Report matched retention probe accuracy.
- [ ] Report per-source and per-label diagnostics.

Done when:

- Plots are reproducible from release artifacts and manifests.
- The analysis does not assume monotonic decline over time.

## Task 18: Release Package

Goal: produce a license-aware V1 release.

Steps:

- [ ] Freeze source revisions and image digests.
- [ ] Freeze fixed-reader version and prompt hashes.
- [ ] Freeze adapter versions.
- [ ] Export transformation manifests.
- [ ] Export task IDs, overlays, normalized trajectories where permitted, and
  derived QA.
- [ ] Do a release-time license review for ToolSandbox-derived artifacts.
- [ ] Do not redistribute SWE-bench upstream repository contents.
- [ ] Finalize `benchmarks/data_card.md`.
- [ ] Package hidden-test inputs separately.

Done when:

- Release artifacts are reproducible from source locks and manifests.
- License notes are explicit for every source.

## Task 19: Paper-Framing Checks

Goal: prevent overclaiming before writing results.

Steps:

- [ ] State that the benchmark measures constraint-memory action decisions, not
  base-task solving.
- [ ] Compare against semantic, procedural, relational, and constraint memory
  without claiming an exhaustive taxonomy.
- [ ] Explain why SCBench + SWE-bench cover coding diversity.
- [ ] Explain why ToolSandbox + tau3-bench cover general stateful workflows.
- [ ] Report position, evidence-distance, and interference effects separately.
- [ ] Avoid claiming all memory systems must monotonically decline over time.

Done when:

- The data card and paper draft make the benchmark claim exactly:
  "whether a memory system can recover and resolve active behavioral contracts
  from an evolving agent history and apply them to a proposed action."

## Immediate Next Task

Start with **Task 0**, then complete **Task 1** and **Task 2** before touching
any source-specific adapter. The first real milestone is a synthetic trajectory
whose hand-written contract graph produces deterministic `allow`, `reject`, and
`ask` labels through the prefix harness.
