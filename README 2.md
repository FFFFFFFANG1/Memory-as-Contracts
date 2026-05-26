# Memory-as-Contracts (MAC) Quickstart

This file is a short quickstart for the clean **Memory-as-Contracts (MAC)**
implementation.

## Setup

```bash
UV_CACHE_DIR=.uv-cache uv sync --dev --no-editable
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=
MAC_LLM_MODEL=
MAC_DB_PATH=.mac/contracts.sqlite
```

## CLI

```bash
UV_CACHE_DIR=.uv-cache uv run --no-editable mac --help
UV_CACHE_DIR=.uv-cache uv run --no-editable mac version
UV_CACHE_DIR=.uv-cache uv run --no-editable mac env --json
```

The current implementation has the MAC package, CLI, config loader, and core
typed data models. Extraction, storage, retrieval, and gating are next steps.
