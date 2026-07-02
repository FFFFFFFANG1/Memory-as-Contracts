#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT_DIR"

set -a
source "bench/.env"
set +a

# Available: cctu, sopbench
BENCH="${BENCH:-cctu}"
# Available: no_memory, long_context
MEMORY_SYSTEM="${MEMORY_SYSTEM:-long_context}"
# Available: 0, 1
DRY_RUN="${DRY_RUN:-0}"
# 0 means all tasks.
LIMIT="${LIMIT:-0}"
OFFSET="${OFFSET:-0}"
# -1 means the last user turn.
TURN_INDEX="${TURN_INDEX:--1}"
MAX_ITERATIONS="${MAX_ITERATIONS:-25}"
MAX_WORKER="${MAX_WORKER:-8}"
TOOL_RETURN_LLM_MODEL="${TOOL_RETURN_LLM_MODEL:-$LLM_MODEL}"
TOOL_RETURN_LLM_BASE_URL="${TOOL_RETURN_LLM_BASE_URL:-$LLM_BASE_URL}"
TOOL_RETURN_LLM_API_KEY_ENV="${TOOL_RETURN_LLM_API_KEY_ENV:-LLM_API_KEY}"
TOOL_RETURN_MAX_ATTEMPTS="${TOOL_RETURN_MAX_ATTEMPTS:-3}"
TOOL_RETURN_MAX_PAYLOAD_CHARS="${TOOL_RETURN_MAX_PAYLOAD_CHARS:-12000}"

RUN_ID="$(date +%s)-$(date +%d-%m-%y)"
RESULTS_ROOT="bench/MAC/${BENCH}/results"
LOG_DIR="${RESULTS_ROOT}/logs"
mkdir -p "$LOG_DIR" "${RESULTS_ROOT}/memory_output" "${RESULTS_ROOT}/memory_output_error" "${RESULTS_ROOT}/memory_grade"

case "$BENCH" in
  cctu)
    TOOL_EXECUTOR="${TOOL_EXECUTOR:-cctu}"
    GRADE_MODULE="bench.MAC.cctu.grade_answer"
    ;;
  sopbench)
    echo "[run] error: BENCH=$BENCH is not configured in run.sh yet"
    exit 1
    ;;
  *)
    echo "[run] error: unknown BENCH=$BENCH (expected cctu or sopbench)"
    exit 1
    ;;
esac

OUTPUT_FILE="${RESULTS_ROOT}/memory_output/${MEMORY_SYSTEM}_${BENCH}_${RUN_ID}.json"
ERROR_OUTPUT_FILE="${RESULTS_ROOT}/memory_output_error/${MEMORY_SYSTEM}_${BENCH}_${RUN_ID}.jsonl"
GRADE_FILE="${RESULTS_ROOT}/memory_grade/${MEMORY_SYSTEM}_${BENCH}_${RUN_ID}.json"
RUN_LOG="$LOG_DIR/${MEMORY_SYSTEM}_${BENCH}_${RUN_ID}.log"

exec > >(tee -a "$RUN_LOG") 2>&1

echo "[run] started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[run] run_id=$RUN_ID bench=$BENCH memory_system=$MEMORY_SYSTEM dry_run=$DRY_RUN limit=$LIMIT offset=$OFFSET max_worker=$MAX_WORKER tool_executor=$TOOL_EXECUTOR"
echo "[run] output_file=$OUTPUT_FILE"
echo "[run] error_output_file=$ERROR_OUTPUT_FILE"
echo "[run] grade_file=$GRADE_FILE"
echo "[run] log=$RUN_LOG"

RUN_ARGS=(
    --bench "$BENCH"
    --memory-system "$MEMORY_SYSTEM"
    --run-id "$RUN_ID"
    --output "$OUTPUT_FILE"
    --offset "$OFFSET"
    --turn-index "$TURN_INDEX"
    --max-iterations "$MAX_ITERATIONS"
    --max-worker "$MAX_WORKER"
    --agent-llm-model "$LLM_MODEL"
    --agent-llm-base-url "$LLM_BASE_URL"
    --agent-llm-api-key-env "LLM_API_KEY"
    --tool-executor "$TOOL_EXECUTOR"
    --tool-return-llm-model "$TOOL_RETURN_LLM_MODEL"
    --tool-return-llm-base-url "$TOOL_RETURN_LLM_BASE_URL"
    --tool-return-llm-api-key-env "$TOOL_RETURN_LLM_API_KEY_ENV"
    --tool-return-max-attempts "$TOOL_RETURN_MAX_ATTEMPTS"
    --tool-return-max-payload-chars "$TOOL_RETURN_MAX_PAYLOAD_CHARS"
)

if [[ "$DRY_RUN" == "1" || "$DRY_RUN" == "true" ]]; then
    RUN_ARGS+=(--dry-run)
fi

if [[ "$LIMIT" != "0" ]]; then
    RUN_ARGS+=(--limit "$LIMIT")
fi

if [[ -n "${RUN_MEMORY_EVAL_ARGS:-}" ]]; then
    # shellcheck disable=SC2206
    EXTRA_RUN_ARGS=($RUN_MEMORY_EVAL_ARGS)
    RUN_ARGS+=("${EXTRA_RUN_ARGS[@]}")
fi

echo "[run] stage=memory_eval"
uv run python -m bench.MAC.scripts.run_memory_eval "${RUN_ARGS[@]}"

if [[ -n "$GRADE_MODULE" ]]; then
    GRADE_ARGS=(
        "$OUTPUT_FILE"
        --bench "$BENCH"
        --run-id "$RUN_ID"
        --memory-system "$MEMORY_SYSTEM"
        --output "$GRADE_FILE"
    )

    if [[ -n "${GRADE_ANSWER_ARGS:-}" ]]; then
        # shellcheck disable=SC2206
        EXTRA_GRADE_ARGS=($GRADE_ANSWER_ARGS)
        GRADE_ARGS+=("${EXTRA_GRADE_ARGS[@]}")
    fi

    echo "[run] stage=grade_answer"
    uv run python -m "$GRADE_MODULE" "${GRADE_ARGS[@]}"
fi

echo "[run] finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
