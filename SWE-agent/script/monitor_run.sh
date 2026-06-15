CONFIG="monitor"
MODEL_NAME="openrouter/deepseek/deepseek-chat-v3-0324"
# MODEL_NAME="openrouter/openai/gpt-5.4-mini"
MODEL="${MODEL_NAME##*/}"
DATASET="swebench"
RUN_ID="${1:-1}"
OUTPUT_DIR="trajectories/${CONFIG}/${DATASET}/${MODEL}/run-${RUN_ID}"
START_INDEX="${2:-0}"
END_INDEX="${3:-500}"

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
    --instances.slice ${START_INDEX}:${END_INDEX} \
    --instances.shuffle=False \
    --output_dir "$OUTPUT_DIR"