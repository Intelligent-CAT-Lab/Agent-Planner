#!/bin/bash
# Script to evaluate attack injection on sampled instances
# Usage: ./eval_sample_inject.sh [RUN_ID]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="openai/gpt-5-mini"
RUN_ID="${1:-1}"

MODEL_NAME="${MODEL##*/}"
SAMPLE_APPROACH="reproducible_patterns"
DATASET="swebench"
PATTERN="dwell"
SAMPLE_DIR="$ROOT_DIR/script/sample-data/samples/$SAMPLE_APPROACH/$DATASET/$MODEL_NAME/$PATTERN"
SAMPLED_FILE="$SAMPLE_DIR/sampled_instances.json"
RESULTS_DIR="$ROOT_DIR/outputs/monitor/$DATASET/$PATTERN/$MODEL_NAME/run-$RUN_ID"

PREDICTION_PATH="$RESULTS_DIR/preds.json"
REPORT_DIR="$RESULTS_DIR/sb-cli-reports"

# Check if sampled instances file exists
if [[ ! -f "$SAMPLED_FILE" ]]; then
    echo "Error: Sampled instances file not found: $SAMPLED_FILE" >&2
    exit 1
fi

# Extract instance IDs from JSON and build a safe regex
INSTANCE_IDS=$(python3 - <<EOF
import json, re
with open("$SAMPLED_FILE", "r") as f:
    instances = json.load(f)
ids = [re.escape(inst["instance_id"]) for inst in instances if "instance_id" in inst]
print("|".join(ids))
EOF
)

if [[ -z "$INSTANCE_IDS" ]]; then
    echo "Error: No instance IDs found in $SAMPLED_FILE" >&2
    exit 1
fi

INSTANCE_COUNT=$(printf '%s\n' "$INSTANCE_IDS" | tr '|' '\n' | wc -l)

echo "================================================================================"
echo "Attack Injection - Sampled Instances"
echo "================================================================================"
echo "Run ID:          $RUN_ID"
echo "Model:           $MODEL"
echo "Instances:       $INSTANCE_COUNT"
echo "Filter (regex):  $INSTANCE_IDS"
echo "================================================================================"

python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path "$PREDICTION_PATH" \
    --run_id "$RUN_ID" \
    --report_dir "$RESULTS_DIR" \
