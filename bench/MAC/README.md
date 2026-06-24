# MAC Benchmark Harness

MAC is the project-owned runtime for evaluating memory systems on constraint benchmarks.

## Layout

```text
bench/MAC/
  agent/              # shared agent loop, memory providers, tool executors
  construct/          # benchmark-specific data construction pipelines
  scripts/            # run + grade entrypoints
  shared/             # cross-benchmark helpers
  cctu/               # CCTU adapter, data, mid_data, results
  memoryarena/        # MemoryArena adapter, tasks, results
  sopbench/           # SOPBench adapter placeholder
```

## Running

```bash
source bench/.env
bash bench/MAC/scripts/run.sh
```

Environment variables:

- `BENCH=cctu|memoryarena|sopbench`
- `MEMORY_SYSTEM=no_memory|long_context`
- `LIMIT`, `OFFSET`, `DRY_RUN`, `MAX_WORKER`

Outputs are written under `bench/MAC/<bench>/results/`.

## CCTU pipeline

Construction scripts live under `bench/MAC/construct/cctu/`. Exports land in
`bench/MAC/cctu/data/`; upstream validators remain in `bench/CCTU/`.
