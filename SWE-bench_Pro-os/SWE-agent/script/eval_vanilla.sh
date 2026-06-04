#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${1:-1}"

MODEL="openrouter/deepseek/deepseek-chat-v3-0324"
# MODEL="openrouter/anthropic/claude-sonnet-4"
# MODEL="openai/gpt-5-mini"
MODEL_NAME="${MODEL##*/}"
SAMPLE_APPROACH="python"
CONFIG="default"
DATASET="swebench-pro"
NUM_WORKERS="${2:-100}"
DOCKERHUB_USERNAME="${3:-jefzda}"

# Build paths
if [ -n "${PATTERN:-}" ]; then
    TRAJ_BASE="$ROOT_DIR/trajectories/$CONFIG/$DATASET/$SAMPLE_APPROACH/$PATTERN/$MODEL_NAME/run-$RUN_ID"
    REPORT_BASE="$ROOT_DIR/reports/$CONFIG/$DATASET/$SAMPLE_APPROACH/$PATTERN/$MODEL_NAME/run-$RUN_ID"
else
    TRAJ_BASE="$ROOT_DIR/trajectories/$CONFIG/$DATASET/$SAMPLE_APPROACH/$MODEL_NAME/run-$RUN_ID"
    REPORT_BASE="$ROOT_DIR/reports/$CONFIG/$DATASET/$SAMPLE_APPROACH/$MODEL_NAME/run-$RUN_ID"
fi

PREDICTION_PATH="$TRAJ_BASE/preds.json"
CONVERTED_PREDICTION_PATH="$TRAJ_BASE/preds_list.json"
RAW_SAMPLE_PATH="$ROOT_DIR/../swe_bench_pro_full.csv"
SCRIPTS_DIR="$ROOT_DIR/../run_scripts"

# Verify prediction file exists
if [[ ! -f "$PREDICTION_PATH" ]]; then
    echo "Error: Prediction file not found: $PREDICTION_PATH" >&2
    exit 1
fi

# Create report directory
mkdir -p "$REPORT_BASE"

# Convert prediction format from dict to list if needed
if [[ ! -f "$CONVERTED_PREDICTION_PATH" ]] || [[ "$PREDICTION_PATH" -nt "$CONVERTED_PREDICTION_PATH" ]]; then
    echo "Converting prediction format..."
    python3 <<EOF
import json

with open("${PREDICTION_PATH}") as f:
    preds = json.load(f)

# Convert dict to list format
if isinstance(preds, dict):
    preds_list = list(preds.values())
else:
    preds_list = preds

with open("${CONVERTED_PREDICTION_PATH}", "w") as f:
    json.dump(preds_list, f, indent=2)

print(f"Converted {len(preds_list)} predictions")
EOF
fi

echo "Configuration:"
echo "  Model: ${MODEL_NAME}"
echo "  Config: ${CONFIG}"
echo "  Dataset: ${DATASET}"
echo "  Sample Approach: ${SAMPLE_APPROACH}"
echo "  Run ID: ${RUN_ID}"
echo "  Prediction Path: ${PREDICTION_PATH}"
echo "  Report Directory: ${REPORT_BASE}"
echo "  Workers: ${NUM_WORKERS}"
echo ""
echo "Starting evaluation..."

cd "$ROOT_DIR/.."
python swe_bench_pro_eval.py \
    --raw_sample_path="$RAW_SAMPLE_PATH" \
    --patch_path="$CONVERTED_PREDICTION_PATH" \
    --output_dir="$REPORT_BASE" \
    --scripts_dir="$SCRIPTS_DIR" \
    --num_workers="$NUM_WORKERS" \
    --dockerhub_username="$DOCKERHUB_USERNAME"

echo ""
echo "✓ Evaluation complete!"
echo "  Results saved to: $REPORT_BASE/eval_results.json"