# SWE-agent Execution Guide for SWE-bench Pro (CORRECT)

## Understanding the Execution Flow

The **correct** way to run SWE-agent is:

1. Create a wrapper config YAML in `sweagent_wrapper_configs/`
2. The config contains the **full `sweagent run-batch` command** as a string
3. Run `python sweagent_wrapper.py <config_name>`
4. The wrapper executes the command and handles output

## Prerequisites

✅ **Already Done**:
- Conda environment: `planner-v1`
- Sample instances: `script/sample-data/samples/python/swebench-pro/sampled_instances.yaml` (266 instances)
- Configs: `config/default.yaml`, `config/monitor.yaml`, `config/refiner.yaml`
- Integration: plan_monitor and plan_refiner fully integrated

## Execution Methods

### Method 1: Docker Execution (Recommended - Follows README)

This is the **official** method described in the SWE-bench_Pro-os/SWE-agent README.

#### Step 1: Setup Environment File

```bash
cd /home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent

# Create .env file with your API keys
cat > .env <<EOF
OPENROUTER_API_KEY=your-actual-api-key-here
OPENAI_BASE_URL=https://openrouter.ai/api/v1
EOF
```

#### Step 2: Verify Modal Credentials

```bash
# Check if modal.toml exists
cat ~/.modal.toml

# Should show:
# [workspace-name]
# token_id = ak-...
# token_secret = as-...
# active = true
```

If missing:
```bash
source /home/shuyang/miniconda3/bin/activate planner-v1
pip install modal
modal setup  # Follow prompts
```

#### Step 3: Create Wrapper Config

Create `sweagent_wrapper_configs/test_vanilla.yaml`:

```yaml
output_dir: sweagent_results/test_vanilla
sweagent_command: |
  sweagent run-batch \
    --config config/default.yaml \
    --output_dir {output_dir} \
    --num_workers 10 \
    --random_delay_multiplier 1 \
    --instances.type file \
    --instances.path script/sample-data/samples/python/swebench-pro/sampled_instances.yaml \
    --instances.slice :10 \
    --instances.shuffle=False \
    --instances.deployment.type=modal \
    --instances.deployment.startup_timeout 1800 \
    --instances.deployment.runtime_timeout 3600 \
    --agent.model.name openrouter/deepseek/deepseek-chat-v3-0324 \
    --agent.model.api_base $OPENAI_BASE_URL \
    --agent.model.api_key $OPENROUTER_API_KEY \
    --agent.model.per_instance_cost_limit 2.0
```

**For Monitor**, create `sweagent_wrapper_configs/test_monitor.yaml`:
```yaml
output_dir: sweagent_results/test_monitor
sweagent_command: |
  sweagent run-batch \
    --config config/monitor.yaml \
    --output_dir {output_dir} \
    --num_workers 10 \
    --random_delay_multiplier 1 \
    --instances.type file \
    --instances.path script/sample-data/samples/python/swebench-pro/sampled_instances.yaml \
    --instances.slice :10 \
    --instances.shuffle=False \
    --instances.deployment.type=modal \
    --instances.deployment.startup_timeout 1800 \
    --instances.deployment.runtime_timeout 3600 \
    --agent.model.name openrouter/deepseek/deepseek-chat-v3-0324 \
    --agent.model.api_base $OPENAI_BASE_URL \
    --agent.model.api_key $OPENROUTER_API_KEY \
    --agent.model.per_instance_cost_limit 2.0
```

**For Refiner**, create `sweagent_wrapper_configs/test_refiner.yaml`:
```yaml
output_dir: sweagent_results/test_refiner
sweagent_command: |
  sweagent run-batch \
    --config config/refiner.yaml \
    --output_dir {output_dir} \
    --num_workers 10 \
    --random_delay_multiplier 1 \
    --instances.type file \
    --instances.path script/sample-data/samples/python/swebench-pro/sampled_instances.yaml \
    --instances.slice :10 \
    --instances.shuffle=False \
    --instances.deployment.type=modal \
    --instances.deployment.startup_timeout 1800 \
    --instances.deployment.runtime_timeout 3600 \
    --agent.model.name openrouter/deepseek/deepseek-chat-v3-0324 \
    --agent.model.api_base $OPENAI_BASE_URL \
    --agent.model.api_key $OPENROUTER_API_KEY \
    --agent.model.per_instance_cost_limit 3.0
```

#### Step 4: Build Docker Image (First Time Only)

```bash
cd /home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent

# Build the image (only needed first time or after swerex_patches changes)
just build
```

This builds `sweagent-image:shuyang` with all dependencies and patches.

#### Step 5: Run Docker Container

```bash
# Start interactive Docker container
just run
```

This command:
- Mounts `~/.modal.toml` for Modal credentials
- Mounts `.env` file for API keys
- Mounts `config/` and `sweagent_wrapper_configs/` (changes sync live)
- Mounts `sweagent_results/` for output
- Drops you into bash shell inside container

#### Step 6: Inside Container - Run SWE-agent

**Run Vanilla (no planner):**
```bash
python sweagent_wrapper.py test_vanilla
```

**Run Monitor:**
```bash
python sweagent_wrapper.py test_monitor
```

**Run Refiner:**
```bash
python sweagent_wrapper.py test_refiner
```

The wrapper will:
1. Read the YAML config
2. Replace `{output_dir}` placeholder with actual path
3. Execute `sweagent run-batch` command via subprocess
4. Save results to `sweagent_results/<config_name>/`

#### Step 7: Exit Container

```bash
exit
```

Results are in `sweagent_results/` on your host machine!

---

### Method 2: Direct CLI Execution (Without Docker)

For quick testing without Docker overhead.

#### Step 1: Activate Environment

```bash
source /home/shuyang/miniconda3/bin/activate planner-v1
cd /home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent
```

#### Step 2: Set Environment Variables

```bash
export OPENROUTER_API_KEY="your-actual-api-key-here"
export OPENAI_BASE_URL="https://openrouter.ai/api/v1"
```

#### Step 3: Create Wrapper Configs

Same as Docker method - create YAML files in `sweagent_wrapper_configs/`

#### Step 4: Run Directly

```bash
# Run vanilla
python sweagent_wrapper.py test_vanilla

# Run monitor
python sweagent_wrapper.py test_monitor

# Run refiner
python sweagent_wrapper.py test_refiner
```

---

## Output Structure

All methods produce the same output structure:

```
sweagent_results/
├── test_vanilla/
│   ├── instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan.traj
│   ├── instance_X.traj
│   └── preds.json                    # Auto-merged predictions
│
├── test_monitor/
│   ├── instance_X.traj
│   ├── instance_X.planner.json       # Monitor interventions!
│   ├── instance_X.monitor_graph.json # State graph (if enabled)
│   └── preds.json
│
└── test_refiner/
    ├── instance_X.traj
    ├── instance_X.planner.json       # Full planner history with costs!
    ├── instance_X.monitor_graph.json
    └── preds.json
```

### planner.json Structure

```json
{
  "summary": {
    "total_interventions": 15,
    "monitor_count": 10,
    "refiner_count": 5,
    "monitor_total_latency_ms": 234.56,
    "refiner_total_latency_ms": 12345.67,
    "refiner_total_input_tokens": 25000,
    "refiner_total_output_tokens": 5000,
    "refiner_total_cost": 0.456
  },
  "interventions": [
    {
      "step": 5,
      "planner_type": "monitor",
      "content": "Warning: Repeated failed command detected...",
      "latency_ms": 23.45
    },
    {
      "step": 6,
      "planner_type": "refiner",
      "content": "[Plan Refiner Guidance]\n\nBased on...",
      "latency_ms": 2345.67,
      "usage": {
        "input_tokens": 5000,
        "output_tokens": 1000,
        "cost": 0.091
      },
      "state_summary": {...}
    }
  ]
}
```

---

## Using the Helper Script (Optional)

The `script/create_wrapper_config.sh` can auto-generate configs:

```bash
cd /home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent/script

# Generate vanilla config
./create_wrapper_config.sh my_test openrouter/deepseek/deepseek-chat-v3-0324 python 25 10
```

This creates `sweagent_wrapper_configs/my_test.yaml` with:
- 25 instances (`:25` slice)
- 10 workers
- Using deepseek model
- Output to `trajectories/default/swebench-pro/python/deepseek-chat-v3-0324/run-1/`

**Then manually edit** the generated config to change:
- `--config config/tool_use.yaml` → `config/monitor.yaml` or `config/refiner.yaml`
- Output directory if desired

---

## Post-Processing

### Step 1: Gather Patches

From SWE-bench_Pro-os root:

```bash
cd /home/shuyang/Agent-Planner/SWE-bench_Pro-os

# Gather vanilla patches
python helper_code/gather_patches.py \
    --directory SWE-agent/sweagent_results/test_vanilla \
    --prefix vanilla \
    --output vanilla_patches.json

# Gather monitor patches
python helper_code/gather_patches.py \
    --directory SWE-agent/sweagent_results/test_monitor \
    --prefix monitor \
    --output monitor_patches.json

# Gather refiner patches
python helper_code/gather_patches.py \
    --directory SWE-agent/sweagent_results/test_refiner \
    --prefix refiner \
    --output refiner_patches.json
```

### Step 2: Evaluate

```bash
# Evaluate vanilla
python swe_bench_pro_eval.py \
    --raw_sample_path=swe_bench_pro_full.csv \
    --patch_path=vanilla_patches.json \
    --output_dir=eval_results/vanilla \
    --scripts_dir=run_scripts \
    --num_workers=100 \
    --dockerhub_username=jefzda

# Same for monitor and refiner...
```

---

## Key Configuration Options Explained

### In Wrapper Config YAML

**`output_dir`**: Where results are saved (relative to SWE-agent directory)
- Example: `sweagent_results/my_run`
- Results appear in: `/home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent/sweagent_results/my_run/`

**`sweagent_command`**: The full `sweagent run-batch` command
- Must include `{output_dir}` placeholder (gets replaced at runtime)
- Can span multiple lines with `|` YAML syntax

### In sweagent_command

**`--config`**: Which agent config to use
- `config/default.yaml` - Vanilla (no planner)
- `config/monitor.yaml` - Monitor only
- `config/refiner.yaml` - Full system (monitor + refiner)

**`--instances.path`**: Path to instances YAML
- `script/sample-data/samples/python/swebench-pro/sampled_instances.yaml`

**`--instances.slice`**: Which instances to run
- `:10` - First 10
- `10:20` - Instances 10-20
- `:` - All instances (remove slice argument entirely)

**`--num_workers`**: Parallel workers
- `10` - Run 10 instances in parallel

**`--agent.model.per_instance_cost_limit`**: Cost limit per instance
- `2.0` - Max $2.00 per instance
- `0` - No limit

**`--agent.model.litellm_model_registry`**: Path to custom model cost registry
- `litellm_model_registry.json` - Custom pricing for models not in litellm's default registry
- Required for OpenRouter models or custom models to track costs accurately

---

## Verification Checklist

After running, verify integration worked:

```bash
# 1. Check output directory exists
ls -la sweagent_results/test_refiner/

# 2. Look for .planner.json files (only with monitor/refiner)
find sweagent_results/test_refiner/ -name "*.planner.json"

# 3. Check a planner file has interventions
cat sweagent_results/test_refiner/instance_*.planner.json | head -50

# 4. Verify summary has refiner data
cat sweagent_results/test_refiner/instance_*.planner.json | grep -A 10 '"summary"'
```

---

## Recommended First Run

```bash
# 1. Navigate to SWE-agent directory
cd /home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent

# 2. Create test config for 5 instances
cat > sweagent_wrapper_configs/quick_test.yaml <<'EOF'
output_dir: sweagent_results/quick_test
sweagent_command: |
  sweagent run-batch \
    --config config/refiner.yaml \
    --output_dir {output_dir} \
    --num_workers 5 \
    --random_delay_multiplier 1 \
    --instances.type file \
    --instances.path script/sample-data/samples/python/swebench-pro/sampled_instances.yaml \
    --instances.slice :5 \
    --instances.shuffle=False \
    --instances.deployment.type=modal \
    --instances.deployment.startup_timeout 1800 \
    --instances.deployment.runtime_timeout 3600 \
    --agent.model.name openrouter/deepseek/deepseek-chat-v3-0324 \
    --agent.model.api_base $OPENAI_BASE_URL \
    --agent.model.api_key $OPENROUTER_API_KEY \
    --agent.model.per_instance_cost_limit 3.0
EOF

# 3. Build and run Docker
just build
just run

# 4. Inside container
python sweagent_wrapper.py quick_test

# 5. Exit and check results
exit
ls -la sweagent_results/quick_test/
find sweagent_results/quick_test/ -name "*.planner.json"
```

---

## Common Issues

### Issue: "Config file not found"

**Cause**: Config not in `sweagent_wrapper_configs/` directory  
**Fix**: Ensure YAML is in correct directory
```bash
ls sweagent_wrapper_configs/your_config.yaml
```

### Issue: "Instances file not found"

**Cause**: Wrong path in `--instances.path`  
**Fix**: Use correct path relative to SWE-agent directory
```bash
# Inside container, path should be:
script/sample-data/samples/python/swebench-pro/sampled_instances.yaml
```

### Issue: No planner.json files created

**Possible causes**:
1. Using `config/default.yaml` (no planner)
2. No monitor rules triggered (check rules config)
3. Monitor/refiner not available (import failed)

**Fix**: 
- Verify using `config/monitor.yaml` or `config/refiner.yaml`
- Check container logs for import errors
- Test plan_monitor import:
```bash
# Inside container
python3 -c "from plan_monitor import StatefulPhaseMonitor; print('OK')"
```

### Issue: Modal deployment fails

**Cause**: Modal credentials not configured  
**Fix**: Run `modal setup` and verify `~/.modal.toml` exists

### Issue: Modal image build fails - Docker Hub authentication

**Cause**: Using wrong Docker Hub username in sampled instances  
**Symptoms**: `Image build for im-XXX failed`, `DOCKER_USERNAME and DOCKER_PASSWORD not set`  
**Fix**: Regenerate instances with official Docker Hub username:
```bash
cd /home/shuyang/Agent-Planner/SWE-bench_Pro-os/SWE-agent/script/sample-data
python sample_py_instances.py --dockerhub_username jefzda --language python
```

The official SWE-bench Pro images are at `jefzda/sweap-images` (public, 1002+ images). Don't use your personal Docker Hub username unless you've built and uploaded all images yourself.

### Issue: Model cost calculation errors / unrecognized model

**Cause**: Model not in litellm's default registry  
**Symptoms**: Cost tracking errors, missing max_tokens warnings  
**Fix**: Ensure `--agent.model.litellm_model_registry litellm_model_registry.json` is in your sweagent command, and the model is defined in the JSON file with pricing info.

---

## Summary: The Correct Workflow

1. **Create wrapper config** in `sweagent_wrapper_configs/<name>.yaml`
   - Set `output_dir`
   - Set full `sweagent run-batch` command with `{output_dir}` placeholder
   - Choose config: `default.yaml`, `monitor.yaml`, or `refiner.yaml`

2. **Run via wrapper**:
   ```bash
   just build && just run  # Docker
   python sweagent_wrapper.py <name>  # Inside container or direct CLI
   ```

3. **Check outputs** in `sweagent_results/<name>/`
   - `.traj` files (always)
   - `.planner.json` files (if monitor/refiner enabled)
   - `.monitor_graph.json` (if `save_monitor_graph: true`)

4. **Gather and evaluate** using helper scripts

---

**This is the official, correct execution method as described in the SWE-bench_Pro-os/SWE-agent README!** 🎯
