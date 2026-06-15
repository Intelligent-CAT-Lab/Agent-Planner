CONFIG="refiner"
# MODEL_NAME="openrouter/mistralai/devstral-small"
# MODEL_NAME="openrouter/openai/gpt-5.4-mini"
# MODEL_NAME="openrouter/minimax/minimax-m2.5"
MODEL_NAME="openrouter/google/gemini-2.5-flash"
# MODEL_NAME="openrouter/ibm-granite/granite-4.1-8b"
MODEL="${MODEL_NAME##*/}"
DATASET="swebench"
RUN_ID="${1:-1}"
VERSION_ID="5"
SAMPLE_APPROACH="${2:-}"
if [[ -n "$SAMPLE_APPROACH" ]]; then
    OUTPUT_DIR="trajectories/${CONFIG}/version-${VERSION_ID}/${DATASET}/${SAMPLE_APPROACH}/${MODEL}/run-${RUN_ID}"
else
    OUTPUT_DIR="trajectories/${CONFIG}/version-${VERSION_ID}/${DATASET}/${MODEL}/run-${RUN_ID}"
fi
PREDICTION_PATH="$OUTPUT_DIR/preds.json"

python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path "$PREDICTION_PATH" \
    --run_id "tmp-${CONFIG}-version-${VERSION_ID}-${MODEL}-run-${RUN_ID}" \
    --report_dir "reports"

    # --run_id "temp-${MODEL}-version-${VERSION_ID}--run-${RUN_ID}" \
