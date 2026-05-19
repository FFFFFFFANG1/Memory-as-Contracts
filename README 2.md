# Memory Use Contracts

Training-free contract layer for memory-mediated coding-agent actions.

## Setup

```bash
uv sync
cp .env.example .env
```

Edit `.env` with an OpenAI-compatible API key, optional base URL, and model:

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=
MUC_LLM_MODEL=
MUC_DB_PATH=.muc/contracts.sqlite
```

## CLI

```bash
uv run muc init
uv run muc ingest --text "Do not edit files under linked_repos unless explicitly asked." --source-kind user_explicit
uv run muc gate --action-class edit_file --target linked_repos/foo.py --intent "fix bug"
uv run muc contracts
uv run muc receipts
```

The v0 Standard path uses a small LLM only at write time for contract extraction. Retrieval
and action-time gating use local SQLite FTS/BM25 plus deterministic rules.
