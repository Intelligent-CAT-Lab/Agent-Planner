ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${1:-1}"
# MODEL="deepseek/deepseek-chat-v3-0324"
MODEL="openai/gpt-5-mini"
MODEL_NAME="${MODEL##*/}"
VERSION_ID="3"
OUT_BASE="$ROOT_DIR/outputs/refiner/version-$VERSION_ID/swebench/$MODEL_NAME/run-$RUN_ID"
PREDICTION_PATH="$OUT_BASE/preds.json"


python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path "$PREDICTION_PATH" \
    --run_id "version-$VERSION_ID-run-$RUN_ID" \
    --report_dir "$OUT_BASE" \