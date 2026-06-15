#!/bin/bash

CONFIG="refiner"
# MODEL_NAME="openrouter/ibm-granite/granite-4.1-8b"
MODEL_NAME="openrouter/google/gemini-2.5-flash"
MODEL="${MODEL_NAME##*/}"
DATASET="swebench"
RUN_ID="${1:-1}"
START_IDX="${2:-0}"
END_IDX="${3:-}"
VERSION_ID="5"
# SAMPLE_APPROACH="patterns_unresolved"
SAMPLE_APPROACH="random"

SAMPLE_FILE="script/sample-data/samples/${SAMPLE_APPROACH}/${DATASET}/${MODEL}/sampled_instances.json"
OUTPUT_DIR="trajectories/${CONFIG}/version-${VERSION_ID}/${DATASET}/${SAMPLE_APPROACH}/${MODEL}/run-${RUN_ID}"

if [ ! -f "$SAMPLE_FILE" ]; then
    echo "Error: Sample file not found: $SAMPLE_FILE"
    exit 1
fi

TOTAL_INSTANCES=$(jq 'length' "$SAMPLE_FILE")

if [ -z "$END_IDX" ]; then
    END_IDX=$TOTAL_INSTANCES
fi

if [ "$START_IDX" -lt 0 ] || [ "$END_IDX" -gt "$TOTAL_INSTANCES" ] || [ "$START_IDX" -ge "$END_IDX" ]; then
    echo "Error: Invalid slice [$START_IDX:$END_IDX] for total $TOTAL_INSTANCES instances"
    exit 1
fi

INSTANCE_FILTER=$(jq -r ".[$START_IDX:$END_IDX][].instance_id" "$SAMPLE_FILE" | paste -sd '|' -)

if [ -z "$INSTANCE_FILTER" ]; then
    echo "Error: No instance IDs found in $SAMPLE_FILE"
    exit 1
fi

NUM_INSTANCES=$(echo "$INSTANCE_FILTER" | tr '|' '\n' | wc -l)
echo "Running refiner on instances [$START_IDX:$END_IDX] = $NUM_INSTANCES instances from $SAMPLE_FILE"
echo "Output directory: $OUTPUT_DIR"

sweagent run-batch \
    --config config/${CONFIG}.yaml \
    --agent.model.api_base https://openrouter.ai/api/v1 \
    --agent.model.name "$MODEL_NAME" \
    --agent.model.api_key $OPENROUTER_API_KEY \
    --num_workers 5 \
    --agent.model.per_instance_cost_limit 2.0 \
    --instances.deployment.docker_args=--memory=10g \
    --agent.model.max_output_tokens 64000 \
    --agent.model.litellm_model_registry litellm_model_registry.json \
    --instances.type swe_bench \
    --instances.subset verified \
    --instances.split test \
    --instances.filter "$INSTANCE_FILTER" \
    --instances.shuffle=False \
    --output_dir "$OUTPUT_DIR"
