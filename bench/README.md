# MAC Benchmark Workspace

This directory holds local benchmark checkouts and the MAC harness.

## Layout

```text
bench/
  CCTU/                 # upstream CCTU checkout (ignored by parent repo)
  SOPBench/             # upstream SOPBench checkout (ignored)
  MAC/                  # project-owned harness and adapted benchmark data
    agent/              # shared MAC runtime
    construct/          # data construction pipelines
    scripts/            # run + grade entrypoints
    cctu/
      bridge.py         # CCTU adapter
      data/             # MAC runtime exports (mac-cctu-*.json)
      mid_data/         # CCTU construction intermediates
      results/          # CCTU run outputs
    sopbench/
      bridge.py
      data/
      results/
```

## Boundaries

- **Upstream repos** under `bench/CCTU` and `bench/SOPBench` stay in their original shape and are ignored by git.
- **MAC-owned artifacts** live under `bench/MAC/<bench>/` with per-benchmark `data/`, `mid_data/` (where applicable), and `results/`.
- **Shared runtime code** lives under `bench/MAC/agent/` and `bench/MAC/scripts/`.

## Environment

Load `bench/.env` before running benchmark setup or evaluation.

Core variables:

- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MAC_LLM_MODEL`
- `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`

Do not commit `.env`, upstream benchmark checkouts, downloaded caches, or generated run outputs.
