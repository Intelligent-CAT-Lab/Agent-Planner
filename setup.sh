#!/usr/bin/env bash
#
# setup.sh — create the two conda environments this project needs.
#
# The two SWE-agent forks share the identical package name `sweagent` and have
# mutually-incompatible `swe-rex` pins, so they CANNOT live in one environment:
#
#   * SWE-bench      -> SWE-agent/                      (swe-rex >= 1.4.0, local Docker)
#   * SWE-bench-Pro  -> SWE-bench_Pro-os/SWE-agent/     (swe-rex[modal] == 1.2.0, Modal)
#
# Each env also gets this repo installed editable, which provides the shared
# LivePlan code: `adapters`, `plan_monitor`, `plan_refiner`.
#
# Usage:
#   bash setup.sh            # create/repair both envs
#   bash setup.sh swebench   # only the SWE-bench env
#   bash setup.sh pro        # only the SWE-bench-Pro env
#
# Re-running is safe: existing envs are updated in place, not recreated.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_VERSION="3.11"

SWEBENCH_ENV="planner"
SWEBENCH_FORK="$REPO_ROOT/SWE-agent"

PRO_ENV="planner-pro"
PRO_FORK="$REPO_ROOT/SWE-bench_Pro-os/SWE-agent"

# --- locate conda ------------------------------------------------------------
if ! command -v conda >/dev/null 2>&1; then
    echo "ERROR: conda not found on PATH. Install Miniconda/Anaconda first." >&2
    exit 1
fi
# shellcheck disable=SC1091
source "$(conda info --base)/etc/profile.d/conda.sh"

# --- helper: build one env ---------------------------------------------------
# $1 = env name, $2 = fork path
#
# We drive each env's own interpreter with `conda run -n <env> python -m pip`
# instead of `conda activate`. Activation does not reliably alter PATH inside a
# non-interactive script, which silently falls back to the system pip; `conda
# run` always targets the right interpreter.
setup_env() {
    local env_name="$1" fork_path="$2"

    if conda env list | awk '{print $1}' | grep -qx "$env_name"; then
        echo "==> Env '$env_name' exists — updating in place."
    else
        echo "==> Creating env '$env_name' (python $PY_VERSION)."
        conda create -y -n "$env_name" "python=$PY_VERSION"
    fi

    local run=(conda run --no-capture-output -n "$env_name")

    echo "==> [$env_name] installing fork: $fork_path"
    "${run[@]}" python -m pip install -e "$fork_path"   # `sweagent` + its pinned swe-rex

    echo "==> [$env_name] installing shared LivePlan code (adapters/plan_monitor/plan_refiner)"
    "${run[@]}" python -m pip install -e "$REPO_ROOT"   # this repo editable

    # The SWE-bench evaluation harness (`python -m swebench.harness.run_evaluation`,
    # used by SWE-agent/script/eval_refiner.sh) lives only in the SWE-bench env; the
    # Pro fork scores through its own Modal-based harness instead.
    if [[ "$env_name" == "$SWEBENCH_ENV" ]]; then
        echo "==> [$env_name] installing SWE-bench eval harness (swebench)"
        "${run[@]}" python -m pip install swebench
    fi

    echo "==> [$env_name] verifying:"
    "${run[@]}" env CHECK_SWEBENCH="$([[ "$env_name" == "$SWEBENCH_ENV" ]] && echo 1)" python - <<'PY'
import importlib.util, os, sweagent, swerex, adapters, plan_monitor, plan_refiner
print(f"    sweagent -> {os.path.dirname(sweagent.__file__)}")
print(f"    swe-rex  -> {swerex.__version__}")
print("    adapters / plan_monitor / plan_refiner: OK")
if os.environ.get("CHECK_SWEBENCH"):
    assert importlib.util.find_spec("swebench.harness.run_evaluation"), "swebench eval harness missing"
    print("    swebench.harness.run_evaluation: OK")
PY

    echo "==> '$env_name' ready."
    echo
}

TARGET="${1:-both}"
case "$TARGET" in
    swebench) setup_env "$SWEBENCH_ENV" "$SWEBENCH_FORK" ;;
    pro)      setup_env "$PRO_ENV"      "$PRO_FORK" ;;
    both)
        setup_env "$SWEBENCH_ENV" "$SWEBENCH_FORK"
        setup_env "$PRO_ENV"      "$PRO_FORK"
        ;;
    *)
        echo "Usage: bash setup.sh [swebench|pro|both]" >&2
        exit 1
        ;;
esac

echo "Done."
echo "  SWE-bench:     conda activate $SWEBENCH_ENV   &&  bash SWE-agent/script/refiner_run.sh"
echo "  SWE-bench-Pro: conda activate $PRO_ENV        &&  bash SWE-bench_Pro-os/SWE-agent/script/run_refiner.sh"
