ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# MODEL="deepseek/deepseek-chat-v3-0324"
MODEL="openai/gpt-5-mini"
MODEL_NAME="${MODEL##*/}"
RUN_ID="${1:-1}"
PATTERN="dwell"
OUT_BASE="$ROOT_DIR/outputs/monitor/swebench/$PATTERN/$MODEL_NAME/run-$RUN_ID"

# Set config path based on model name
if [ "$MODEL_NAME" = "gpt-5-mini" ]; then
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/monitor_swebench_med_reasoning.yaml"
else
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/monitor_swebench.yaml"
fi

mini-extra swebench \
  --model "$MODEL" \
  --model-class openrouter \
  --subset verified \
  --split test \
  --config "$CONFIG_PATH" \
  --output "$OUT_BASE" \
  --filter "sympy__sympy-20428" \
  --workers 4 \
