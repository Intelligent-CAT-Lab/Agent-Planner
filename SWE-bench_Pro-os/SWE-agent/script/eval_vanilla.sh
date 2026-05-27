ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${1:-1}"
MODEL="openrouter/deepseek/deepseek-chat-v3-0324"
# MODEL="openrouter/anthropic/claude-sonnet-4"
# MODEL="openai/gpt-5-mini"
MODEL_NAME="${MODEL##*/}"
# VERSION_ID="5"
SAMPLE_APPROACH="python"
CONFIG="default"
DATASET="swebench"
# PATTERN="oscillation"
if [ -n "${PATTERN:-}" ]; then
    OUT_BASE="$ROOT_DIR/trajectories/$CONFIG/$DATASET/$SAMPLE_APPROACH/$PATTERN/$MODEL_NAME/run-$RUN_ID"
else
    OUT_BASE="$ROOT_DIR/trajectories/$CONFIG/$DATASET/$SAMPLE_APPROACH/$MODEL_NAME/run-$RUN_ID"
fi
PREDICTION_PATH="$OUT_BASE/preds.json"


python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path "$PREDICTION_PATH" \
    --run_id "tmp-$MODEL_NAME-version-$VERSION_ID-$PATTERN-run-$RUN_ID" \
    --report_dir "$OUT_BASE" 