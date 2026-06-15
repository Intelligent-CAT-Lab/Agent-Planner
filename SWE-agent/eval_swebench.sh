RUN_ID="${1:-1}"
CONFIG="oscillation"
MODEL_NAME=openrouter/google/gemini-2.5-flash
MODEL="${MODEL_NAME##*/}"
RESULTS_DIR="trajectories/$CONFIG/exp-${RUN_ID}/$MODEL"
# PREDICTION_PATH="$RESULTS_DIR/preds.json"
PREDICTION_PATH="/home/shuyang/Agent-Planner/gemini-2.5-flash/preds.json"
python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified \
    --predictions_path "$PREDICTION_PATH" \
    --run_id "tmp-selected-default-${MODEL}-run-${RUN_ID}" \
    --report_dir "reports"
