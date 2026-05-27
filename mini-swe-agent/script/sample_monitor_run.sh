#!/bin/bash
# Script to run monitor integration on sampled instances
# Usage: ./sample_run_monitor.sh [RUN_ID]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL="openai/gpt-5-mini"
# MODEL="mistralai/devstral-small"
RUN_ID="${1:-1}"

MODEL_NAME="${MODEL##*/}"
SAMPLE_APPROACH="reproducible_patterns"
DATASET="swebench"
PATTERN="plan_compliance"
SAMPLE_DIR="$ROOT_DIR/script/sample-data/samples/$SAMPLE_APPROACH/$DATASET/$MODEL_NAME/$PATTERN"
# SAMPLE_DIR="$ROOT_DIR/script/sample-data/samples/general/run-$RUN_ID"
SAMPLED_FILE="$SAMPLE_DIR/sampled_instances.json"

# Optionally separate runs in output dirs if you want:
OUT_BASE="$ROOT_DIR/outputs/monitor/$DATASET/$PATTERN/$MODEL_NAME/run-$RUN_ID"

# Set config path based on model name
if [ "$MODEL_NAME" = "gpt-5-mini" ]; then
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/monitor_swebench_med_reasoning.yaml"
else
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/monitor_swebench.yaml"
fi

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
echo "Monitor Integration - Sampled Instances"
echo "================================================================================"
echo "Run ID:          $RUN_ID"
echo "Model:           $MODEL"
echo "Instances:       $INSTANCE_COUNT"
echo "Config:          $CONFIG_PATH"
echo "Output:          $OUT_BASE"
echo "Filter (regex):  $INSTANCE_IDS"
echo "================================================================================"

mini-extra swebench \
  --model "$MODEL" \
  --model-class openrouter \
  --subset verified \
  --split test \
  --config "$CONFIG_PATH" \
  --output "$OUT_BASE" \
  --filter "$INSTANCE_IDS" \
  --workers 4