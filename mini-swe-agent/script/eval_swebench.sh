ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${1:-1}"
MODEL="openai/gpt-5-mini"
MODEL_NAME="${MODEL##*/}"
OUT_BASE="$ROOT_DIR/outputs/default/swebench/$MODEL_NAME/$RUN_ID"
PREDICTION_PATH="$OUT_BASE/preds.json"


python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path "$PREDICTION_PATH" \
    --run_id "tmp-$RUN_ID" \
    --report_dir "$OUT_BASE" \