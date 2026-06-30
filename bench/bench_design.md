# MAC-Bench Design Notes

## Reporting Metrics

MAC-Bench reports a small set of metrics that separate task completion from
contract-memory behavior. The main table should use six metrics:

| Metric | Level | Meaning |
| --- | --- | --- |
| `ACC` | Task | The final task outcome is correct. |
| `RSP` | Task | The run produced a terminal, gradable response. |
| `CFR` | Contract | Overall contract-decision correctness. |
| `F1` | Contract | Harmonic mean of contract precision and recall. |
| `Precision` | Contract | Followed contracts that are currently active. |
| `Recall` | Contract | Currently active contracts that were followed. |

`ACC` and `RSP` capture whether the agent completed the benchmark task at all.
`CFR`, `F1`, `Precision`, and `Recall` capture whether the agent applied the
right remembered contracts.

We intentionally do not put constraint-level accuracy in the main table because
it overlaps with `CFR`. Legacy benchmark-specific metrics such as CCTU
`SR`/`PSR`/`SSR` can remain in detailed JSON outputs or appendix tables, but the
main MAC-Bench comparison should focus on the six metrics above.

## Contract Confusion Matrix

For memory grading, each contract unit is evaluated as an active-vs-obsolete
decision:

| | Agent follows | Agent ignores |
| --- | --- | --- |
| Active/current contract | `TP` | `FN` |
| Obsolete/inactive contract | `FP` | `TN` |

From this matrix:

```text
Precision = TP / (TP + FP)
Recall    = TP / (TP + FN)
F1        = 2 * Precision * Recall / (Precision + Recall)
CFR       = (TP + TN) / (TP + FP + FN + TN)
```

Use zero-division-safe implementations: if a denominator is zero, emit `null`
for that metric and include support counts in the detail output.

## CCTU Mapping

CCTU noise grading already has unit-level outcomes:

- `anchor_followed`: baseline constraint correctly followed (`TP` side).
- `anchor_missed`: baseline constraint missed (`FN` side).
- `noise_followed`: inapplicable/noise constraint incorrectly followed (`FP` side).
- `noise_ignored`: inapplicable/noise constraint correctly ignored (`TN` side).

For MAC-Bench reporting:

```text
TP = anchor_followed count
FN = anchor_missed count
FP = noise_followed count
TN = noise_ignored count
```

`ACC` and `RSP` are task-level metrics. `CFR`, `F1`, `Precision`, and `Recall`
are computed from the contract-unit counts above.

## SOPBench Temporal Mapping

SOPBench temporal histories test whether the agent follows the **final SOP at
evaluation time** rather than **superseded constraint trees** introduced earlier
in the conversation.

### Anchor vs Noise (Constraint-Tree Definition)

For SOPBench, anchor and noise are defined at the **constraint-tree level**:

| Label | Definition |
| --- | --- |
| **Anchor** | The **final** user-goal constraint tree at evaluation time (`g_t`). This is the effective SOP the agent should follow when answering the last user turn. |
| **Noise** | Any **earlier** user-goal constraint tree that appeared in temporal history but is **not** part of the final anchor tree at eval time. These are obsolete / superseded SOP revisions. |

At grading time:

```text
anchor tree   = final user-goal constraint tree at eval
noise trees   = historical user-goal constraint trees \ anchor tree
```

The grader flattens trees into contract units for MAC-style scoring: walk each
tree into dependency singles and graph precall actions, label units against the
final anchor tree, then replay the agent trajectory with strict SOPBench domain
semantics.

### Unit-Level Outcomes

For each exported contract unit:

- An **anchor** unit (`expected_should_apply=true`) that the agent follows is `TP`.
- An anchor unit that the agent fails to follow is `FN`.
- A **noise** unit (`expected_should_apply=false`) that the agent still follows is `FP`.
- A noise unit that the agent ignores is `TN`.

This makes `Precision` a stale-memory penalty and `Recall` an update-missing
penalty relative to the final anchor SOP.

Important interpretation note for SOPBench `ACC`: it follows SOPBench's native
definition of success, where `action_called_correctly` means the observed user
goal outcome matches `action_should_succeed`. A task with
`action_should_succeed=false` can therefore receive `ACC=1` when the agent
correctly avoids a successful user-goal call.

## Benchmark Construction

Both MAC slices follow the same high-level pattern: start from an upstream
benchmark task, introduce temporal contract variation through multi-turn user
history, hold out one final evaluation turn, and grade memory systems on whether
the agent applies active contracts while ignoring obsolete ones.

### CCTU Construction Pipeline

**Goal.** Turn static CCTU tool-use tasks into long-horizon memory benchmarks
where constraints arrive incrementally and only the final turn is evaluated.

1. **Task adaptation.** Import upstream CCTU tasks and normalize them into MAC
   task records: constraint-free system prompts, structured constraint metadata,
   tool schemas, and task summaries.

2. **Per-constraint rule-graph generation.** For each task constraint, generate
   a baseline rule graph and noisy variants. Each graph encodes executable
   validation logic and dependency structure for that constraint thread.

3. **Graph validation.** Filter invalid or duplicate graphs before they enter
   the temporal pipeline.

4. **Intra-task constraint merging.** Merge per-constraint histories into one
   temporal constraint sequence per task using randomized insertion. Later
   constraints may only appear after the insertion point of earlier ones,
   preserving a plausible revision order while shuffling cross-constraint
   arrival.

5. **User-turn history synthesis.** Populate long conversational histories that
   introduce constraints over many turns. Style and domain context are sampled
   per agent; the final turn remains the held-out evaluation query.

6. **Contract-spec export.** Export anchor vs obsolete units from the merged
   constraint graph. Anchor units correspond to constraints active at eval
   time; noise units correspond to constraints that appeared historically but
   are no longer active.

7. **Runtime packaging.** Materialize task records, user-turn histories, tool
   registries, and grading manifests for memory-system evaluation.

**Active vs obsolete (CCTU).** A constraint node in the merged graph is **anchor**
if it is active on the final evaluation turn; otherwise it is **noise**. Units
are flattened from graph nodes and replayed with python or structured
validators.

### SOPBench Temporal Construction Pipeline

**Goal.** Turn static SOPBench SOPs into temporal memory benchmarks where
user-goal constraint trees evolve over conversation and only the final tree is
valid at evaluation time.

1. **Task sampling and SOP extraction.** Sample a fixed number of SOPBench tasks
   across domains. Expand each task into per-action SOP rules, domain system
   prompts, tool schemas, and the native user-goal dependency tree.

2. **Anchor constraint selection.** For each task, select a set of anchor
   constraints: mandatory user-goal and action-path rules, plus additional
   sampled constraints from the domain pool. These define the baseline SOP
   fragments that will be mutated downstream.

3. **Action-level temporal noise generation.** For each anchor, generate noisy
   SOP revisions by structurally mutating action-local dependency trees and
   compiled action graphs. Revisions are plausible superseded drafts of the same
   business rule, not unrelated tasks.

4. **Temporal sequence assembly.** Deduplicate action-level noise fan-out, merge
   revisions from different actions into one shuffled temporal sequence per task,
   and compile the cumulative user-goal constraint tree and directed action
   graph after each revision. Adjacent-turn semantic deltas are recorded for
   history population.

5. **User-turn history population.** Build three-phase histories per task:
   - **Warmup:** a short LLM-generated preamble that establishes the baseline
     SOP framing for the user goal.
   - **Normal:** one user turn per semantic dependency delta, introducing or
     revising SOP rules in conversational form, plus carryover filler turns.
   - **Evaluation:** the original task query on the last turn.

6. **Contract-spec export.** Replay the temporal sequence, collect all
   historical user-goal trees, and label the **final tree as anchor** and every
   distinct earlier tree as **noise**. Flatten trees into grading units when
   computing contract metrics.

7. **Runtime packaging.** Export task records, user-turn histories, per-task
   tool registries, and noise-eval manifests for memory-system evaluation.

**Active vs obsolete (SOPBench).** At the tree level, each task contributes one
**anchor constraint graph** (final `g_t`) and several **noisy constraint graphs**
from historical revisions. At grading time, trees are flattened into contract
units, but benchmark-scale reporting uses graph counts and ratios.

### Shared Evaluation Protocol

All MAC memory runs use the same agent-loop shape:

1. Inject retrieved memory from prior user turns.
2. Present the current evaluation user turn.
3. Allow tool use until a terminal response tool call.
4. Grade task completion (`ACC`, `RSP`) and contract decisions (`CFR`, `F1`,
   `Precision`, `Recall`).

Default turn policy is **last user turn**. Historical turns are never shown
directly to the agent; they are only available through the memory system under
test.

Supported memory baselines:

- `no_memory`
- `long_context`
- `bm25`
- `embedding`
- `rrf`
- `mac`
- `mem0`

### Grading Oracle Summary

| Bench | Task-level oracle | Contract oracle |
| --- | --- | --- |
| CCTU | Answer / task completion checks | Anchor vs obsolete nodes in merged constraint graph; validator replay |
| SOPBench | SOPBench strict replay (`success`, `dirgraph_satisfied`, database match) | Final anchor constraint tree vs historical noise trees |

## Benchmark Statistics

Scale numbers below are from the current 200-task CCTU and 200-task SOPBench
slices.

### Overview

| Quantity | CCTU | SOPBench (temporal) |
| --- | ---: | ---: |
| Evaluation tasks | 200 | 200 |
| Domains / task sources | 4 CCTU source splits | 7 SOPBench domains |
| User-turn histories | 200 | 200 |
| Mean history turns per task | 188.3 | 82.8 |
| Median history turns per task | 181.0 | 83.0 |
| Evaluation turns per task | 1 (last turn) | 1 (last turn) |
| Contract units (graded) | 5,772 | — |
| Active / anchor units | 805 (14.0%) | 200 (20.9%) |
| Obsolete / noise units | 4,967 (86.0%) | 758 (79.1%) |

CCTU reports flattened contract units. SOPBench reports **constraint graphs**
in the anchor/noise rows: one final anchor graph per task, plus unique
historical noisy graphs accumulated across temporal replay.

Across the two slices: **400 evaluation tasks**, **5,772 CCTU contract units**,
and **958 SOPBench constraint graphs** (200 anchor + 758 noise).

### CCTU Slice

| Statistic | Value |
| --- | ---: |
| Tasks | 200 |
| Source split | Single-Hop 50, Multi-Hop 50, Parallel Single-Hop 50, Parallel Multi-Hop 50 |
| Inferred difficulty | easy 44, normal 105, hard 51 |
| Mean constraints per task | 4.6 |
| Median constraints per task | 4 |
| Min / max constraints per task | 1 / 9 |
| Mean tools per task | 9.3 |
| Median tools per task | 9 |
| Mean history user turns | 188.3 |
| Median history user turns | 181.0 |
| Min / max history user turns | 54 / 402 |
| Contract units | 5,772 |
| Anchor units | 805 |
| Noise units | 4,967 |
| Mean units per task | 28.9 |
| Median units per task | 28 |
| Min / max units per task | 7 / 59 |
| Unit evaluator types | python 5,445; structured 326; unsupported 1 |

### SOPBench Temporal Slice

| Statistic | Value |
| --- | ---: |
| Tasks | 200 |
| SOPBench domains | bank 32, dmv 23, healthcare 30, hotel 47, library 16, online_market 42, university 10 |
| Unique user goals | 54 |
| Mean tools per task | 24.0 |
| Median tools per task | 25 |
| Min / max tools per task | 17 / 31 |
| Mean total user turns per task | 83.8 |
| Median total user turns per task | 83 |
| Min / max total user turns per task | 46 / 134 |
| Mean warmup turns per task | 3.4 |
| Mean normal (temporal) turns per task | 79.4 |
| Evaluation turns per task | 1 |
| Total warmup turns | 683 |
| Total normal turns | 15,876 |
| Total evaluation turns | 200 |
| `action_should_succeed=true` tasks | 62 (31.0%) |
| `action_should_succeed=false` tasks | 138 (69.0%) |
| Mean sampled anchor constraints per task | 13.3 |
| Median sampled anchor constraints per task | 13 |
| Temporal-noise revisions generated | 3,484 |
| Mean temporal replay depth per task | 20.1 |
| Median temporal replay depth per task | 20 |
| Anchor constraint graphs | 200 |
| Noise constraint graphs | 758 |
| Anchor-graph share | 20.9% |
| Noise-graph share | 79.1% |
| Mean noise graphs per task | 3.8 |
| Median noise graphs per task | 4.0 |
| Min / max noise graphs per task | 0 / 9 |
| Mean singles per anchor graph | 6.9 |
| Median singles per anchor graph | 6 |

Constraint graphs by domain:

| Domain | Tasks | Anchor graphs | Noise graphs |
| --- | ---: | ---: | ---: |
| bank | 32 | 32 | 110 |
| dmv | 23 | 23 | 71 |
| healthcare | 30 | 30 | 133 |
| hotel | 47 | 47 | 167 |
| library | 16 | 16 | 44 |
| online_market | 42 | 42 | 190 |
| university | 10 | 10 | 43 |

### Suggested Paper Tables

For a main paper, the most useful MAC-Bench summary is:

1. **Benchmark scale table**: tasks, history length, and anchor/noise distribution
   (CCTU: contract units; SOPBench: constraint graphs).
2. **Domain breakdown table**: SOPBench tasks and constraint graphs by domain.
3. **Metric table**: `ACC`, `RSP`, `CFR`, `F1`, `Precision`, `Recall`.
4. **Memory-system table**: rows for each memory baseline listed above.

For an appendix, additionally report:

- CCTU source split and difficulty counts
- SOPBench temporal construction counts (noise revisions, replay depth)
- Per-task distributions of history length and noise-graph count
