ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# MODEL="deepseek/deepseek-chat-v3-0324"
MODEL="openai/gpt-5-mini"
MODEL_NAME="${MODEL##*/}"
VERSION_ID="3"
OUT_BASE="$ROOT_DIR/outputs/refiner/version-$VERSION_ID/swebench/$MODEL_NAME/run-1"

# Set config path based on model name
if [ "$MODEL_NAME" = "gpt-5-mini" ]; then
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/refiner_swebench_med_reasoning.yaml"
else
  CONFIG_PATH="$ROOT_DIR/src/minisweagent/config/extra/refiner_swebench.yaml"
fi

mini-extra swebench \
  --model "$MODEL" \
  --model-class openrouter \
  --subset verified \
  --split test \
  --config "$CONFIG_PATH" \
  --output "$OUT_BASE" \
  --filter "django__django-13128" \
  --workers 4 \
