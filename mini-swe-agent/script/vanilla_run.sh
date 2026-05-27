ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${1:-1}"
MODEL="openai/gpt-5-mini"
MODEL_NAME="${MODEL##*/}"
OUT_BASE="$ROOT_DIR/outputs/default/swebench/$MODEL_NAME/$RUN_ID"

# Set config path based on model name
if [ "$MODEL_NAME" = "gpt-5-mini" ]; then
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/swebench_med_reasoning.yaml"
else
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/swebench.yaml"
fi

mini-extra swebench \
  --model "$MODEL" \
  --model-class openrouter \
  --subset verified \
  --split test \
  --config "$CONFIG_PATH" \
  --output "$OUT_BASE" \
  --filter "django__django-14631" \
  --workers 5 \
