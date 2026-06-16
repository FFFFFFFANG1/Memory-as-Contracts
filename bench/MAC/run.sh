#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

Model_Name="${BENCH_PRIMARY_MODEL:-}"
Model_Name_URL="${OPENAI_BASE_URL:-}"
Model_Name_API_Key="${OPENAI_API_KEY:-}"

Evaluator_Model_Backbone="${BENCH_EVAL_MODEL:-${BENCH_PRIMARY_MODEL:-}}"
Evaluator_URL="${BENCH_EVAL_BASE_URL:-${OPENAI_BASE_URL:-}}"
Evaluator_API_Key="${BENCH_EVAL_API_KEY:-${OPENAI_API_KEY:-}}"

if [[ -z "${Model_Name}" || -z "${Model_Name_URL}" || -z "${Model_Name_API_Key}" ]]; then
  echo "Missing BENCH_PRIMARY_MODEL / OPENAI_BASE_URL / OPENAI_API_KEY in ${ROOT}/.env" >&2
  exit 1
fi

UV=(uv run --project "${ROOT}" --group agentif python)

# data/eval.json: 458 single-turn tasks, no example_driven, no multi-turn
# Full 707-sample set: data/eval_full.json (regenerate subset via scripts/filter_single_no_example.py)
AGENTIF_INPUT_DIR="${AGENTIF_INPUT_DIR:-data}"

"${UV[@]}" code4eval/0.prediction_api.py \
  --input_dir "${AGENTIF_INPUT_DIR}" \
  --output_dir "results/prediction/${Model_Name}" \
  --llm_backbone "${Model_Name}" \
  --llm_url "${Model_Name_URL}" \
  --api_key "${Model_Name_API_Key}" \
  --cache ".cache/evaluation/${Model_Name}.pkl"

"${UV[@]}" code4eval/1.evaluation_api.py \
  --input_file "results/prediction/${Model_Name}/eval.json" \
  --output_dir "results/scores/${Model_Name}_${Evaluator_Model_Backbone}" \
  --llm_backbone "${Evaluator_Model_Backbone}" \
  --llm_url "${Evaluator_URL}" \
  --api_key "${Evaluator_API_Key}" \
  --cache ".cache/evaluation/${Evaluator_Model_Backbone}.pkl"
