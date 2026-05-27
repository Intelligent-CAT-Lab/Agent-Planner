CONFIG="default"
MODEL_NAME="openrouter/deepseek/deepseek-chat-v3-0324"
MODEL="${MODEL_NAME##*/}"
DATASET="swebench"
RUN_ID="${1:-1}"
VERSION_ID="5"
OUTPUT_DIR="trajectories/${CONFIG}/version-${VERSION_ID}/${DATASET}/${MODEL}/run-${RUN_ID}"
PREDICTION_PATH="$OUTPUT_DIR/preds.json"

python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path "$PREDICTION_PATH" \
    --run_id "tmp-${CONFIG}-version-${VERSION_ID}-${MODEL}-run-${RUN_ID}" \
    --report_dir "reports"