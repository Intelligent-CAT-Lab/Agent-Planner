set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RUN_ID="${1:-1}"
# if not provided, will run on all instances in the sampled file. Otherwise, can specify a slice of instances to run on, e.g. "0" "100" to run on the first 100 instances.
START_IDX="${2:-}"
END_IDX="${3:-}"

MODEL="openrouter/mistralai/devstral-small"
MODEL_NAME="${MODEL##*/}"
CONFIG="refiner"
VERSION_ID="5"
DATASET="swebench-pro"
SAMPLE_APPROACH="python"
COST=2.0

if [ -n "${PATTERN:-}" ]; then
    SAMPLE_DIR="$ROOT_DIR/script/sample-data/samples/$SAMPLE_APPROACH/$DATASET/$MODEL_NAME/$PATTERN"
    OUT_BASE="$ROOT_DIR/trajectories/$CONFIG/version-$VERSION_ID/$DATASET/$SAMPLE_APPROACH/$PATTERN/$MODEL_NAME/run-$RUN_ID"
elif [ "$SAMPLE_APPROACH" = "python" ]; then
    SAMPLE_DIR="$ROOT_DIR/script/sample-data/samples/$SAMPLE_APPROACH/$DATASET"
    OUT_BASE="$ROOT_DIR/trajectories/$CONFIG/version-$VERSION_ID/$DATASET/$SAMPLE_APPROACH/$MODEL_NAME/run-$RUN_ID"
else
    SAMPLE_DIR="$ROOT_DIR/script/sample-data/samples/$SAMPLE_APPROACH/$DATASET/$MODEL_NAME"
    OUT_BASE="$ROOT_DIR/trajectories/$CONFIG/version-$VERSION_ID/$DATASET/$SAMPLE_APPROACH/$MODEL_NAME/run-$RUN_ID"
fi

SAMPLED_FILE="$SAMPLE_DIR/sampled_instances.yaml"
# Check if sampled instances file exists
if [[ ! -f "$SAMPLED_FILE" ]]; then
    echo "Error: Sampled instances file not found: $SAMPLED_FILE" >&2
    exit 1
fi
# Extract instance IDs from YAML and print a safe regex
INSTANCE_IDS=$(python3 - <<EOF
import yaml
with open("$SAMPLED_FILE", "r") as f:
    instances = yaml.safe_load(f)
ids = [inst["instance_id"] for inst in instances if "instance_id" in inst]
print("|".join(ids))
EOF
)

CONFIG_PATH="$ROOT_DIR/config/$CONFIG.yaml"

# Determine slice string for sweagent command
if [ -n "$START_IDX" ] && [ -n "$END_IDX" ]; then
    SLICE="$START_IDX:$END_IDX"
elif [ -n "$START_IDX" ]; then
    SLICE="$START_IDX:"
elif [ -n "$END_IDX" ]; then
    SLICE=":$END_IDX"
else
    SLICE=":"
fi

# Generate wrapper config name
WRAPPER_CONFIG_NAME="run_${CONFIG}_version${VERSION_ID}_${SAMPLE_APPROACH}_run${RUN_ID}"
WRAPPER_CONFIG_PATH="$ROOT_DIR/sweagent_wrapper_configs/${WRAPPER_CONFIG_NAME}.yaml"

# Ensure wrapper config directory exists
mkdir -p "$ROOT_DIR/sweagent_wrapper_configs"

# Generate wrapper config YAML
cat > "$WRAPPER_CONFIG_PATH" <<EOF
# Auto-generated wrapper config
# Config: ${CONFIG}
# Model: ${MODEL}
# Language: ${SAMPLE_APPROACH}
# Run ID: ${RUN_ID}
# Slice: ${SLICE}

output_dir: ${OUT_BASE}
sweagent_command: |
  python -c "import modal; modal.enable_output()" && \\
  sweagent run-batch \\
    --config ${CONFIG_PATH} \\
    --output_dir {output_dir} \\
    --num_workers 4 \\
    --agent.model.per_instance_cost_limit ${COST} \\
    --agent.model.litellm_model_registry litellm_model_registry.json \\
    --random_delay_multiplier 1 \\
    --instances.type file \\
    --instances.path ${SAMPLED_FILE} \\
    --instances.slice ${SLICE} \\
    --instances.shuffle=False \\
    --instances.deployment.type=modal \\
    --instances.deployment.startup_timeout 1800 \\
    --instances.deployment.runtime_timeout 3600 \\
    --agent.model.name ${MODEL} \\
    --agent.model.api_base https://openrouter.ai/api/v1 \\
    --agent.model.api_key \$OPENROUTER_API_KEY
EOF

echo "✓ Generated wrapper config: ${WRAPPER_CONFIG_PATH}"
echo ""
echo "Configuration:"
echo "  Model: ${MODEL}"
echo "  Config: ${CONFIG}"
echo "  Language: ${SAMPLE_APPROACH}"
echo "  Sampled file: ${SAMPLED_FILE}"
echo "  Slice: ${SLICE}"
echo "  Output: ${OUT_BASE}"
echo ""
echo "Running sweagent via wrapper..."

# Run sweagent via wrapper
cd "$ROOT_DIR"
python sweagent_wrapper.py "$WRAPPER_CONFIG_NAME"