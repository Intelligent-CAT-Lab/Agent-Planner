CONFIG="monitor"
# MODEL_NAME="openrouter/minimax/minimax-m2.5"
MODEL_NAME="openrouter/deepseek/deepseek-chat-v3-0324"
MODEL="${MODEL_NAME##*/}"
DATASET="swebench"
RUN_ID="${1:-1}"
OUTPUT_DIR="trajectories/${CONFIG}/${DATASET}/${MODEL}/run-${RUN_ID}"
PREDICTION_PATH="$OUTPUT_DIR/preds.json"

python -m swebench.harness.run_evaluation \
	--dataset_name SWE-bench/SWE-bench_Verified \
	--predictions_path "$PREDICTION_PATH" \
	--run_id "tmp-${CONFIG}-${MODEL}-run-${RUN_ID}" \
	--report_dir "reports"
